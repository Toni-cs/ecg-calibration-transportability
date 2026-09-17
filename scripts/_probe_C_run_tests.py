"""无控制台环境下运行 tests/ 测试（pytest 在无 console 时崩溃；测试类非 unittest.TestCase，
需手工实例化。fixture 参数跳过）"""
import glob, os, sys, importlib.util, inspect, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

ok = fail = skip = 0
errs = []
for f in sorted(glob.glob("tests/test_*.py")):
    m = os.path.basename(f)[:-3]
    try:
        spec = importlib.util.spec_from_file_location(m, f)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[m] = mod
        spec.loader.exec_module(mod)
    except Exception as e:
        print("IMPORT-FAIL", m, type(e).__name__, e)
        continue

    jobs = []  # (label, callable)
    for n in dir(mod):
        o = getattr(mod, n)
        if n.startswith("test_") and inspect.isfunction(o):
            jobs.append((n, o))
        elif inspect.isclass(o) and (n.startswith("Test") or n.endswith("Test")):
            for mn in dir(o):
                if mn.startswith("test_"):
                    jobs.append((f"{n}.{mn}", (o, mn)))

    nfile = 0
    for label, obj in jobs:
        try:
            if isinstance(obj, tuple):
                cls, mn = obj
                try:
                    inst = cls()
                except TypeError:
                    skip += 1
                    continue
                fn = getattr(inst, mn)
            else:
                fn = obj
            params = list(inspect.signature(fn).parameters.values())
            if any(p.default is inspect.Parameter.empty for p in params):
                skip += 1
                continue
            fn()
            ok += 1
            nfile += 1
        except Exception as e:
            fail += 1
            errs.append((m, label, type(e).__name__, str(e)[:140]))
    print(f"  {m}: 通过 {nfile} / 收集 {len(jobs)}")

print(f"\nSUMMARY pass={ok} fail={fail} skipped={skip}")
for e in errs[:10]:
    print("  FAIL", e)
