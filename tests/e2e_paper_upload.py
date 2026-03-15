"""E2E test: Paper Upload → Extract Strategy → Save & Run → Backtester.

Starts a Streamlit server, navigates through the full paper upload pipeline,
and verifies the strategy backtester renders results.
"""

import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

APP_PORT = 8502
APP_URL = f"http://localhost:{APP_PORT}"
STARTUP_TIMEOUT = 15
# DeepSeek extraction + mapping + generation can take a while
PIPELINE_TIMEOUT = 120_000  # 120s
BACKTEST_TIMEOUT = 60_000   # 60s


def wait_for_server(port: int, timeout: int = STARTUP_TIMEOUT):
    """Wait for the Streamlit server to be ready."""
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"Server not ready on port {port} after {timeout}s")


def main():
    # Start Streamlit server
    print("Starting Streamlit server...")
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app/main.py",
         "--server.port", str(APP_PORT),
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        wait_for_server(APP_PORT)
        print(f"Server ready at {APP_URL}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # ----------------------------------------------------------
            # Step 1: Navigate to Paper Upload page
            # ----------------------------------------------------------
            print("Navigating to Paper Upload...")
            page.goto(f"{APP_URL}/Paper_Upload", wait_until="networkidle",
                      timeout=30_000)
            # Wait for the page to render
            page.wait_for_timeout(3000)

            # Verify we're on the Paper Upload page
            content = page.content()
            assert "Paper Upload" in content, "Paper Upload page did not load"
            print("  Paper Upload page loaded.")

            # ----------------------------------------------------------
            # Step 2: Click Extract Strategy
            # ----------------------------------------------------------
            print("Clicking Extract Strategy...")
            extract_btn = page.get_by_role("button", name="Extract Strategy")
            assert extract_btn.is_visible(), "Extract Strategy button not found"
            extract_btn.click()

            # Wait for the pipeline to complete (AI calls take time)
            # Look for the status to show "complete" or for results to appear
            print("  Waiting for AI pipeline to complete (this takes ~30-60s)...")
            page.wait_for_timeout(5000)  # initial wait for status to appear

            # Wait for either "Extraction complete" or "Save & Run" button
            try:
                page.get_by_role("button", name="Save & Run").wait_for(
                    state="visible", timeout=PIPELINE_TIMEOUT
                )
                print("  Pipeline complete — Save & Run button visible.")
                is_feasible = True
            except Exception:
                # Check if it stopped as not feasible
                content = page.content()
                if "NOT FEASIBLE" in content or "not feasible" in content.lower():
                    print("  Pipeline complete — strategy is not feasible (expected for demo 1? checking...)")
                    is_feasible = False
                else:
                    raise AssertionError("Pipeline did not complete within timeout")

            # Verify strategy spec is displayed
            content = page.content()
            assert "Strategy Spec" in content or "Strategy Name" in content, \
                "Strategy spec not displayed after extraction"
            print("  Strategy spec displayed.")

            # Verify feasibility section is displayed
            assert "Feasibility" in content or "FEASIBLE" in content, \
                "Feasibility section not displayed"
            print("  Feasibility section displayed.")

            if not is_feasible:
                print("  Strategy not feasible — cannot test Save & Run flow.")
                print("PARTIAL PASS: Extraction and feasibility check work.")
                browser.close()
                return

            # ----------------------------------------------------------
            # Step 3: Click Save & Run
            # ----------------------------------------------------------
            print("Clicking Save & Run...")
            save_btn = page.get_by_role("button", name="Save & Run")
            save_btn.click()

            # Should navigate to Strategy Backtester
            print("  Waiting for Strategy Backtester to load...")
            page.wait_for_timeout(5000)

            # Wait for the backtest to run (spinner → results)
            # Look for metric cards or the Paper Strategy banner
            try:
                page.wait_for_function(
                    """() => {
                        const text = document.body.innerText;
                        return text.includes('Paper Strategy') ||
                               text.includes('Total P&L') ||
                               text.includes('Sharpe');
                    }""",
                    timeout=BACKTEST_TIMEOUT,
                )
                print("  Backtester loaded with results.")
            except Exception:
                # Take a screenshot for debugging
                page.screenshot(path="/tmp/e2e_backtester_fail.png")
                content = page.content()
                # Check for errors
                if "error" in content.lower() or "Error" in content:
                    print(f"  ERROR detected on page. Screenshot at /tmp/e2e_backtester_fail.png")
                raise AssertionError("Backtester did not show results within timeout")

            # Verify key elements on the backtester page
            content = page.content()

            assert "Paper Strategy" in content, \
                "Paper Strategy banner not found on backtester page"
            print("  Paper Strategy banner displayed.")

            # Check for backtest metrics
            has_metrics = ("Sharpe" in content or "Total P" in content
                          or "Win Rate" in content)
            assert has_metrics, "No backtest metrics found on backtester page"
            print("  Backtest metrics displayed.")

            print("\nPASS: Full E2E flow works — Paper Upload → Extract → Save & Run → Backtester")
            browser.close()

    finally:
        print("Shutting down server...")
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
