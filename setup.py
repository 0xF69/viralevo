#!/usr/bin/env python3
"""
ViralEvo — First-Run Setup Validator
Checks all system requirements and initializes the database.
Run ONCE before onboarding: python3 setup.py
"""
import subprocess, sys, os, json, platform
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.environ.get("VIRALEVO_DATA_DIR",
    Path.home() / ".openclaw" / "workspace" / "viralevo"))

REQUIRED_NODE = (18, 0)
REQUIRED_PYTHON = (3, 10)

def check(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label}{' — ' + detail if detail else ''}")
    return ok

def require_version(cmd, min_ver, name):
    """Check version with robust error handling."""
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
        # Handle: "Python 3.10.12", "v18.20.0", "3.10.12", "openclaw 2026.1"
        ver_str = out.split()[-1].lstrip("vV").split(".")[:len(min_ver)]
        ver = tuple(int(x) for x in ver_str)
        ok = ver >= min_ver
        return check(f"{name} {out}", ok, f"need >= {'.'.join(map(str,min_ver))}")
    except subprocess.TimeoutExpired:
        return check(f"{name} timed out", False, f"need >= {'.'.join(map(str,min_ver))}")
    except FileNotFoundError:
        return check(f"{name} not found", False, f"need >= {'.'.join(map(str,min_ver))}")
    except Exception:
        # Last resort: check if command exists at all
        try:
            result = subprocess.run([cmd[0], "--version"], capture_output=True, timeout=3)
            if result.returncode == 0:
                return check(f"{name} (detected, version unreadable)", True)
        except Exception:
            pass
        return check(f"{name} not found", False, f"need >= {'.'.join(map(str,min_ver))}")

def main():
    print("\n🔧 ViralEvo v0.6.4 — Setup Check\n")
    all_ok = True

    print("Layer 1 — Operating System")
    check(f"OS: {platform.system()} {platform.release()}", True)

    print("\nLayer 2 — Runtime Environments")
    all_ok &= require_version(["node", "--version"], REQUIRED_NODE, "Node.js")
    all_ok &= require_version(["python3", "--version"], REQUIRED_PYTHON, "Python")

    print("\nLayer 3 — Application Framework")
    try:
        oc = subprocess.check_output(["openclaw", "--version"], stderr=subprocess.DEVNULL, text=True).strip()
        check(f"OpenClaw {oc}", True)
    except Exception:
        check("OpenClaw not found", False, "install from https://openclaw.ai")
        all_ok = False

    print("\nLayer 4 — API Credentials")
    env_path = BASE_DIR / ".env"
    root_env = Path(".env")
    key = os.environ.get("TAVILY_API_KEY")
    if not key and env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TAVILY_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key and root_env.exists():
        for line in root_env.read_text().splitlines():
            if line.startswith("TAVILY_API_KEY="):
                key = line.split("=", 1)[1].strip()
    check("TAVILY_API_KEY", bool(key), "not found — add to .env" if not key else f"found ({'*'*8}{key[-4:]})")
    if not key:
        print("    → Get free key at https://tavily.com")

    print("\nFile Structure")
    # Runtime dirs (in BASE_DIR = data location)
    for d in ["data", "logs", "reports"]:
        p = BASE_DIR / d
        p.mkdir(parents=True, exist_ok=True)
        check(f"~/.openclaw/…/{d}/", True)
    # Skill dirs (in SKILL_DIR = installation location, read-only after install)
    for d in ["scripts", "templates", "examples"]:
        p = SKILL_DIR / d
        ok = p.exists()
        check(f"skill/{d}/", ok, "missing — reinstall skill" if not ok else "")

    print("\nDatabase")
    try:
        import sys
        sys.path.insert(0, str(SKILL_DIR))
        from db.init_db import init, DB_PATH
        init()
        check(f"SQLite initialized at {DB_PATH}", True)
    except Exception as e:
        check("Database init failed", False, str(e))
        all_ok = False

    print("\nNode Dependencies")
    nm = SKILL_DIR / "node_modules"
    pkg = SKILL_DIR / "package.json"
    if pkg.exists() and not nm.exists():
        print("  Installing npm packages…")
        subprocess.run("npm install", shell=True, cwd=SKILL_DIR)
    check("node_modules", nm.exists())

    print("\n" + "─"*40)
    if all_ok:
        print("✅ All checks passed! Start onboarding:")
        print("   node scripts/onboarding.js")
        print("   — or tell your OpenClaw agent —")
        print("   'Start ViralEvo setup'")
    else:
        print("❌ Some checks failed. Fix the issues above before continuing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
