# 2026/27 LaLiga Second-Yellow Report

Public report: https://hattrick-msn.github.io/laliga-2026-report/

Season card leaderboards and match booking events are read from public LaLiga pages. The Opta Analyst comparison covers the named verified player only; it does not claim full leaderboard equivalence.

GitHub Actions checks for updates every 10 minutes (scheduling may be delayed). The page checks the published snapshot every 60 seconds. All match times are displayed in Beijing time. Failed fetches retain cached data and are shown in the report.

Run `python laliga-report-server.py --refresh-once` and `python build-laliga-report.py` to update the snapshot. Python 3.12 standard library is sufficient. The Swiss HTML file is the layout source used by the builder; only the LaLiga report and its public assets are deployed.
