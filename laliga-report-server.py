"""Refresh the 2026/27 LaLiga report from public official page data."""
from __future__ import annotations

import argparse
import copy
import json
import os
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://www.laliga.com"
REPORT_FILE = "2026-2027-laliga-second-yellow-report.html"
CACHE = ROOT / "report-assets/laliga-cache.json"
EXPORT = ROOT / "report-assets/laliga-report.json"
SEASON = "2026"
OPTA_SEASON = "830epggffy1nfkfyrtpqdwhlg"
OPTA_ALTI = "https://theanalyst.com/players/1295/adria-alti/stats"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and (attrs.get("id") == "__NEXT_DATA__" or attrs.get("type") == "application/json"):
            self.current = [attrs, ""]

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_scripts(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LaLiga-Report/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                parser = PageParser()
                parser.feed(response.read().decode("utf-8"))
            return parser.scripts
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def page(path):
    for attrs, raw in fetch_scripts(BASE + path):
        if attrs.get("id") == "__NEXT_DATA__":
            data = json.loads(raw)
            props = data["props"]["pageProps"]
            config = data["props"].get("globalData", {}).get("COMPETITION_CONFIG", {})
            if config.get("primera-division", {}).get("stats", SEASON) != SEASON:
                raise ValueError("Official site has changed season; retaining 2026/27 snapshot")
            if props.get("statusCode", 200) != 200:
                raise ValueError("Official page returned an error")
            return props
    raise ValueError("Official structured page data missing")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def rank_players(players, key):
    rows = [dict(row) for row in players if row[key] > 0]
    rows.sort(key=lambda r: (-r[key], r["name"].casefold(), r["playerId"]))
    previous = None
    rank = 0
    for index, row in enumerate(rows, 1):
        if row[key] != previous:
            rank, previous = index, row[key]
        row["rank"] = rank
    return rows


def parse_players(props):
    rows = []
    if not props.get("playersStats"):
        raise ValueError("Player statistics missing")
    for item in props["playersStats"]:
        extra = item["extra_info"]
        stats = {s["name"]: s["stat"] for s in item["stats"]}
        rows.append({
            "playerId": item["opta_player_id"], "name": extra["name"],
            "team": extra["teamNickname"], "teamSlug": extra["teamSlug"],
            "playerSlug": extra["slug"], "shield": extra.get("teamShield", ""),
            "yellow": int(stats.get("yellow_cards", 0)),
            "doubleYellow": int(stats.get("red_cards_2nd_yellow", 0)),
            "red": int(stats.get("total_red_cards", 0)),
        })
    return rows


def fetch_rankings():
    combined = {}
    for category, primary in [("yellow-cards", "total_yellow_card"), ("red-cards", "total_red_card")]:
        page_number = 1
        while True:
            props = page(f"/en-GB/stats/laliga-easports/{category}/page/{page_number}")
            if str(props.get("season")) != SEASON:
                raise ValueError("Leaderboard season changed")
            rows = props.get("statsData", {}).get("player_rankings")
            if not rows:
                raise ValueError("Leaderboard page missing")
            for row in rows:
                stats = {v["name"]: v["stat"] for v in row["stats"]}
                if int(stats.get(primary, 0)) <= 0:
                    continue
                team = row["team"]
                combined[row["slug"]] = {
                    "playerId": row.get("opta_id") or str(row["id"]), "name": row["name"],
                    "team": team["nickname"], "teamSlug": team["slug"], "playerSlug": row["slug"],
                    "shield": team.get("shield", {}).get("resizes", {}).get("small", ""),
                    "yellow": int(stats.get("total_yellow_card", 0)),
                    "doubleYellow": int(stats.get("total_second_yellow", 0)),
                    "red": int(stats.get("total_red_card", 0)),
                }
            last_stats = {v["name"]: v["stat"] for v in rows[-1]["stats"]}
            if int(last_stats.get(primary, 0)) == 0 or page_number * 20 >= props["statsData"]["total"]:
                break
            page_number += 1
            if page_number > 100:
                raise ValueError("Leaderboard pagination exceeded expected range")
    if not combined:
        raise ValueError("No card records returned")
    return {key: rank_players(combined.values(), key) for key in ("yellow", "doubleYellow", "red")}


def event_order(event):
    return (int(event.get("minute", 0)), int(event.get("second", 0)), int(event.get("id", 0)))


def person_key(event):
    lineup = event.get("lineup", {})
    return (lineup.get("team", {}).get("id"), lineup.get("person", {}).get("name"))


def extract_match(props):
    match = props["match"]
    if str(match["season"]["opta_id"]) != SEASON or match["competition"]["slug"] != "primera-division":
        raise ValueError("Unexpected competition or season")
    if not isinstance(props.get("events"), list):
        raise ValueError("Match events missing")
    cards = sorted([e for e in props["events"] if e.get("match_event_kind", {}).get("collection") == "booking"], key=event_order)
    events = []
    for second in cards:
        if second["match_event_kind"]["name"] != "Second Yellow":
            continue
        first = next((e for e in cards if person_key(e) == person_key(second) and e["match_event_kind"]["name"] == "Yellow" and event_order(e) < event_order(second)), None)
        team_id, name = person_key(second)
        team = match["home_team"] if team_id == match["home_team"]["id"] else match["away_team"]
        events.append({
            "playerId": f"{team_id}:{name}", "person": name, "team": team["nickname"],
            "role": "球员", "first": first.get("clock") if first else None,
            "second": second.get("clock"), "reason": "第二张黄牌；具体原因未在事件字段注明",
            "reasonOriginal": "Second Yellow", "eventId": str(second["id"]),
        })
    if not events:
        return None
    # Match timestamps are UTC; display Beijing time consistently, including date rollover.
    kickoff = datetime.fromisoformat(match["date"]).astimezone(timezone(timedelta(hours=8)))
    return {
        "id": str(match["id"]), "slug": match["slug"], "date": kickoff.strftime("%Y-%m-%d"),
        "time": kickoff.strftime("%H:%M"), "kickoff": match["date"],
        "stage": f"第{match['gameweek']['week']}轮", "type": "regular",
        "status": "已结束" if match["status"] in {"FullTime", "Awarded"} else "进行中",
        "home": match["home_team"]["nickname"], "away": match["away_team"]["nickname"],
        "homeShield": match["home_team"].get("shield", {}).get("url", ""),
        "awayShield": match["away_team"].get("shield", {}).get("url", ""),
        "homeScore": match["home_score"], "awayScore": match["away_score"], "events": events,
    }


class ReportStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.refreshing = False
        self.cache = {"teams": {}, "matches": {}, "lastCatalog": 0}
        self.data = {"season": "2026/2027", "source": "LALIGA / Opta", "lastSync": None,
                     "failures": [], "matches": [], "checkedMatches": 0, "eligibleMatches": 0,
                     "cardLeaderboards": {k: [] for k in ("yellow", "doubleYellow", "red")}}
        for path, target in [(CACHE, "cache"), (EXPORT, "data")]:
            if path.exists():
                try:
                    setattr(self, target, json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    pass

    def report(self):
        with self.lock:
            result = copy.deepcopy(self.data)
            result["refreshing"] = self.refreshing
            return result

    def fetch_team(self, team, force):
        slug = team["slug"]
        old = self.cache["teams"].get(slug, {})
        result = copy.deepcopy(old)
        errors = []
        for key, suffix, interval in [("players", "stats", 600), ("fixtures", "results", 60)]:
            if not force and time.time() - old.get(key + "At", 0) < interval:
                continue
            try:
                props = page(f"/en-GB/clubs/{slug}/{suffix}")
                if key == "players":
                    result[key] = parse_players(props)
                else:
                    if str(props.get("season")) != SEASON or not isinstance(props.get("matches"), list):
                        raise ValueError("Unexpected season or missing schedule")
                    result[key] = [m for m in props["matches"] if m["competition"]["slug"] == "primera-division" and str(m.get("season", {}).get("opta_id", SEASON)) == SEASON]
                result[key + "At"] = time.time()
            except Exception as error:
                errors.append(f"{slug} {suffix}: {type(error).__name__}: {error}")
        return slug, result, errors

    def refresh(self, force=False):
        if not self.refresh_lock.acquire(blocking=False):
            return
        with self.lock:
            self.refreshing = True
        failures = []
        try:
            if force or time.time() - self.cache.get("lastCatalog", 0) > 3600:
                catalog = page("/en-GB/stats/laliga-easports/team")
                teams = [t for t in catalog.get("sortedTeams", []) if t.get("slug") != "all"]
                if str(catalog.get("season")) != SEASON or len(teams) != 20:
                    raise ValueError("Expected 20 LaLiga teams for 2026/27")
                self.cache["catalog"] = teams
                self.cache["lastCatalog"] = time.time()
            teams = self.cache["catalog"]
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(self.fetch_team, t, force) for t in teams]
                for future in as_completed(futures):
                    slug, result, errors = future.result()
                    self.cache["teams"][slug] = result
                    failures.extend(errors)
            fixtures, players = {}, {}
            for t in teams:
                team = self.cache["teams"].get(t["slug"], {})
                for m in team.get("fixtures", []):
                    if m.get("status") in {"FullTime", "Awarded", "FirstHalf", "HalfTime", "SecondHalf", "ExtraTime"}:
                        fixtures[str(m["id"])] = m
                for player in team.get("players", []):
                    players[(player["playerId"], player["teamSlug"])] = player
            due = []
            for mid, fixture in fixtures.items():
                old = self.cache["matches"].get(mid, {})
                interval = 21600 if fixture["status"] in {"FullTime", "Awarded"} else 60
                if force or old.get("status") != fixture["status"] or time.time() - old.get("checkedAt", 0) >= interval:
                    due.append(fixture)
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(page, "/en-GB/match/" + m["slug"]): m for m in due}
                for future in as_completed(futures):
                    fixture = futures[future]
                    try:
                        props = future.result()
                        self.cache["matches"][str(fixture["id"])] = {
                            "checkedAt": time.time(), "status": props["match"]["status"], "match": extract_match(props)}
                    except Exception as error:
                        failures.append(f"比赛 {fixture['id']}: {type(error).__name__}: {error}")
            matches = [entry["match"] for mid, entry in self.cache["matches"].items() if mid in fixtures and entry.get("match")]
            matches.sort(key=lambda m: (m["date"], m["time"]), reverse=True)
            boards = self.data.get("cardLeaderboards", {})
            if force or time.time() - self.cache.get("rankingsAt", 0) >= 600:
                try:
                    boards = fetch_rankings()
                    self.cache["rankingsAt"] = time.time()
                except Exception as error:
                    failures.append(f"官网牌榜: {type(error).__name__}: {error}")
            expected = sum(p["doubleYellow"] for p in players.values())
            observed = sum(len(m["events"]) for m in matches)
            if expected != observed:
                failures.append(f"待复核：牌榜两黄离场 {expected} 次，已读取比赛事件 {observed} 次")
            comparison = self.data.get("optaComparison")
            if force or not comparison or time.time() - comparison.get("checkedAt", 0) >= 3600:
                try:
                    rows = []
                    for attrs, raw in fetch_scripts(OPTA_ALTI):
                        obj = json.loads(raw)
                        if isinstance(obj, dict):
                            rows.extend(r for r in obj.get("rows", []) if r.get("id") == OPTA_SEASON and "yellow_cards" in r)
                    if len(rows) != 1:
                        raise ValueError("Opta 2026/27 season row missing")
                    row = rows[0]
                    comparison = {"name": "Adrià Alti", "url": OPTA_ALTI, "checkedAt": time.time(),
                                  "checkedOn": now_iso(), "yellow": row["yellow_cards"],
                                  "doubleYellow": row["second_yellows"], "red": row["red_cards"]}
                except Exception as error:
                    failures.append(f"Opta 实例对照: {type(error).__name__}: {error}")
            checked = sum(mid in self.cache["matches"] for mid in fixtures)
            data = {"season": "2026/2027", "source": "LALIGA / Opta", "lastSync": now_iso(),
                    "lastCompleteSync": self.data.get("lastCompleteSync"), "failures": failures,
                    "matches": matches, "checkedMatches": checked, "eligibleMatches": len(fixtures),
                    "checkedTeams": sum(bool(self.cache["teams"].get(t["slug"], {}).get("players")) for t in teams),
                    "cardLeaderboards": boards, "optaComparison": comparison, "refreshing": False}
            if not failures:
                data["lastCompleteSync"] = data["lastSync"]
            with self.lock:
                self.data = data
                atomic_json(EXPORT, data)
                atomic_json(CACHE, self.cache)
        except Exception as error:
            with self.lock:
                self.data["failures"] = [f"刷新失败: {type(error).__name__}: {error}"]
                atomic_json(EXPORT, self.data)
        finally:
            with self.lock:
                self.refreshing = False
            self.refresh_lock.release()

    def schedule(self):
        while True:
            self.refresh()
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8776)
    parser.add_argument("--refresh-once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    store = ReportStore()
    if args.refresh_once:
        store.refresh(force=args.force)
        data = store.report()
        print(json.dumps({k:v for k,v in data.items() if k not in {"matches", "cardLeaderboards"}}, ensure_ascii=False))
        raise SystemExit(1 if data["failures"] else 0)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/report":
                if urllib.parse.parse_qs(parsed.query).get("refresh") == ["1"]:
                    threading.Thread(target=store.refresh, kwargs={"force": True}, daemon=True).start()
                body = json.dumps(store.report(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                if parsed.path == "/":
                    self.path = "/" + REPORT_FILE
                super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(target=store.schedule, daemon=True).start()
    print(f"http://127.0.0.1:{args.port}/{REPORT_FILE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
