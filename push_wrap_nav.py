"""
Wrap_NAV.xlsx 수동 Push 버튼
더블클릭하면 현재 Wrap_NAV.xlsx를 GitHub에 push합니다.
"""
import subprocess
import os
import sys
import datetime
import tkinter as tk
from tkinter import messagebox

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO_DIR)

def push():
    btn.config(state='disabled', text='푸시 중...')
    root.update()

    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # 1. git add
        subprocess.run(['git', 'add', 'Wrap_NAV.xlsx'], capture_output=True, timeout=10)

        # 2. git commit
        commit = subprocess.run(
            ['git', 'commit', '-m', f'update: Wrap_NAV.xlsx ({now})'],
            capture_output=True, text=True, timeout=10
        )

        if 'nothing to commit' in commit.stdout:
            messagebox.showinfo('알림', '변경사항이 없습니다.')
            btn.config(state='normal', text='Push Wrap_NAV')
            return

        # 3. git pull --rebase (충돌 시 우리 파일 유지)
        pull = subprocess.run(
            ['git', 'pull', '--rebase', 'origin', 'main'],
            capture_output=True, text=True, timeout=30
        )

        if pull.returncode != 0:
            # 충돌 발생 시 - Wrap_NAV는 우리 걸로, 나머지는 remote 걸로
            subprocess.run(['git', 'checkout', '--ours', 'Wrap_NAV.xlsx'], capture_output=True, timeout=10)
            # 생성 파일들은 remote 걸로
            for f in ['index.html', 'wrap.html', 'portfolio_data.json', 'market_alert.html']:
                subprocess.run(['git', 'checkout', '--theirs', f], capture_output=True, timeout=10)
            subprocess.run(['git', 'add', '-A'], capture_output=True, timeout=10)
            subprocess.run(['git', '-c', 'core.editor=true', 'rebase', '--continue'],
                         capture_output=True, timeout=10, env={**os.environ, 'GIT_EDITOR': 'true'})

        # 4. git push
        push_result = subprocess.run(
            ['git', 'push', 'origin', 'main'],
            capture_output=True, text=True, timeout=30
        )

        if push_result.returncode == 0:
            status.config(text=f'Push 완료 ({now})', fg='#00aa00')
            messagebox.showinfo('성공', f'Wrap_NAV.xlsx push 완료!\n{now}')
        else:
            status.config(text='Push 실패', fg='red')
            messagebox.showerror('실패', f'Push 실패:\n{push_result.stderr[:200]}')

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
