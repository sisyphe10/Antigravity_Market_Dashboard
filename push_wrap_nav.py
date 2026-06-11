"""
Wrap_NAV.xlsx 수동 Push 버튼
더블클릭하면 현재 Wrap_NAV.xlsx를 GitHub에 push합니다.
"""
import os
import sys
import logging
import datetime
import tkinter as tk
from tkinter import messagebox

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO_DIR)
sys.path.insert(0, os.path.join(REPO_DIR, 'scripts'))
import local_safe_push  # merge-only push policy (no rebase, no add -A)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(os.path.join(REPO_DIR, 'watch_wrap_nav.log'), encoding='utf-8')],
)


def push():
    btn.config(state='disabled', text='푸시 중...')
    root.update()

    try:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        ok = local_safe_push.safe_push(REPO_DIR, logging.getLogger())
        if ok:
            status.config(text=f'Push 완료 ({now})', fg='#00aa00')
            messagebox.showinfo('성공', f'Wrap_NAV.xlsx push 완료!\n{now}')
        elif os.path.exists(os.path.join(REPO_DIR, local_safe_push.HOLD_FILE)):
            status.config(text='보류 (양쪽 수정)', fg='red')
            messagebox.showerror(
                '보류',
                '원격과 로컬이 둘 다 Wrap_NAV.xlsx를 수정했습니다.\n'
                f'{local_safe_push.HOLD_FILE} 파일의 수동 해결 절차를 따라주세요.',
            )
        else:
            status.config(text='Push 실패', fg='red')
            messagebox.showerror('실패', 'Push 실패 - watch_wrap_nav.log 확인')

    except Exception as e:
        status.config(text='오류 발생', fg='red')
        messagebox.showerror('오류', str(e))

    btn.config(state='normal', text='Push Wrap_NAV')

# GUI
root = tk.Tk()
root.title('Wrap_NAV Push')
root.geometry('300x150')
root.resizable(False, False)

tk.Label(root, text='Wrap_NAV.xlsx', font=('Segoe UI', 12, 'bold')).pack(pady=(20, 5))

btn = tk.Button(root, text='Push Wrap_NAV', command=push,
                font=('Segoe UI', 11), bg='#1e40af', fg='white',
                padx=20, pady=8, cursor='hand2')
btn.pack(pady=10)

status = tk.Label(root, text='', font=('Segoe UI', 9))
status.pack()

root.mainloop()
