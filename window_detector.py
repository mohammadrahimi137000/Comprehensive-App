
import win32gui
import win32process
import win32con


def get_open_windows():
    windows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd).strip()

        if not title:
            return

        if win32gui.IsIconic(hwnd):
            return

        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)

            windows.append({
                "hwnd": hwnd,
                "title": title,
                "process_id": process_id,
            })

        except Exception:
            pass

    win32gui.EnumWindows(callback, None)

    return windows


def show_windows():
    windows = get_open_windows()

    print("\n========== پنجره‌های باز ویندوز ==========\n")

    for index, window in enumerate(windows, start=1):
        print(
            f"{index}. {window['title']} "
            f"| PID: {window['process_id']} "
            f"| ID: {window['hwnd']}"
        )

    print("\n=========================================")
    print(f"تعداد پنجره‌های شناسایی‌شده: {len(windows)}")


if __name__ == "__main__":
    show_windows()
