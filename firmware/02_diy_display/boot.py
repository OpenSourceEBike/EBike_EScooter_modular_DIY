# boot.py — simple crash-loop breaker using RTC memory
import machine

MAX_BAD = 2
BAD_CAUSES = (machine.WDT_RESET, machine.HARD_RESET)

rtc = machine.RTC()

def get_bad():
    try:
        data = rtc.memory()
        return int(data) if data else 0
    except Exception:
        return 0

def set_bad(v):
    try:
        rtc.memory(str(int(v)))
    except Exception:
        pass

cause = machine.reset_cause()
print("Reset cause:", cause)

bad = get_bad()

if cause in BAD_CAUSES:
    bad += 1
else:
    bad = 0  # clean reset clears the streak

set_bad(bad)
print("Bad boot streak:", bad)

if bad >= MAX_BAD:
    print("Crash loop detected -> skipping main.py (REPL only)")
    raise SystemExit
