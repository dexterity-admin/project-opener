try:
    import app
    print("Syntax check passed.")
except ImportError as e:
    print(f"Import Error: {e}")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
except Exception as e:
    # It might fail to run because of GUI requirements (no display), but parsing should work
    print(f"Runtime Error (Expected if no GUI): {e}")
