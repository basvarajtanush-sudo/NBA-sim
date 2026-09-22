import nflreadpy as nfl

schedule = nfl.load_schedules([2026])
print(schedule.head(10))