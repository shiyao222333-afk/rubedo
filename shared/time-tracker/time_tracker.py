#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Time Tracker — 时间记录工具 v0.1
tkinter 版本，无需浏览器，最轻量。
用法：双击运行，或 python time_tracker.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
import os
from datetime import datetime

# ── 配置 ─────────────────────────────────────────────
SAVE_DIR = r"D:\Program Files\文档\打工\一人公司\数据\时间审计"
PHASES = ["接单", "沟通", "画2D", "效果图", "修改交付"]
# ────────────────────────────────────────────────────────


class TimeTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("时间记录 · Time Tracker v0.1")
        self.root.geometry("400x520")
        self.root.resizable(False, False)

        self.phase_running = {p: False for p in PHASES}
        self.phase_start = {p: 0.0 for p in PHASES}
        self.phase_elapsed = {p: 0.0 for p in PHASES}   # 累计秒数
        self.phase_label = {}
        self.phase_btn = {}

        self._build_ui()
        self._update_clock()

    # ── UI ──────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # 订单号
        f_order = ttk.Frame(self.root)
        f_order.pack(fill="x", **pad)
        ttk.Label(f_order, text="订单号：", font=("", 10)).pack(side="left")
        self.order_var = tk.StringVar()
        self.order_entry = ttk.Entry(f_order, textvariable=self.order_var, width=22)
        self.order_entry.pack(side="left", fill="x", expand=True)

        # 分隔线
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=12, pady=6)

        # 5 个环节按钮
        for phase in PHASES:
            f = ttk.Frame(self.root)
            f.pack(fill="x", **pad)

            btn = ttk.Button(f, text=f"▶ {phase}", width=14,
                             command=lambda p=phase: self._toggle(p))
            btn.pack(side="left")
            self.phase_btn[phase] = btn

            lbl = ttk.Label(f, text="00:00:00", font=("Consolas", 10), width=12)
            lbl.pack(side="right")
            self.phase_label[phase] = lbl

        # 分隔线
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=12, pady=8)

        # 合计
        f_total = ttk.Frame(self.root)
        f_total.pack(fill="x", **pad)
        ttk.Label(f_total, text="合计", font=("", 10, "bold")).pack(side="left")
        self.total_label = ttk.Label(f_total, text="00:00:00",
                                     font=("Consolas", 11, "bold"), width=12)
        self.total_label.pack(side="right")

        # 保存按钮
        ttk.Button(self.root, text="💾 保存并新建",
                    command=self._save).pack(pady=12, ipadx=20, ipady=4)

        # 状态栏
        self.status = ttk.Label(self.root, text="就绪", relief="sunken", anchor="w")
        self.status.pack(side="bottom", fill="x")

    # ── 计时逻辑 ────────────────────────────────────
    def _toggle(self, phase):
        if self.phase_running[phase]:          # 停止
            elapsed = time.time() - self.phase_start[phase]
            self.phase_elapsed[phase] += elapsed
            self.phase_running[phase] = False
            self.phase_btn[phase].config(text=f"▶ {phase}")
            self.status.config(text=f"⏹ {phase} 已停止")
        else:                                   # 开始
            # 检查是否有其他正在计时的环节（一次只计一个）
            running = [p for p in PHASES if self.phase_running[p]]
            if running:
                messagebox.showwarning("提示",
                    f"「{running[0]}」正在计时，请先停止它。\n（一次只记录一个环节）")
                return
            self.phase_start[phase] = time.time()
            self.phase_running[phase] = True
            self.phase_btn[phase].config(text=f"⏹ {phase}")
            self.status.config(text=f"▶ {phase} 计时中…")

    def _format(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _update_clock(self):
        """每秒刷新显示。"""
        for phase in PHASES:
            if self.phase_running[phase]:
                now = self.phase_elapsed[phase] + (time.time() - self.phase_start[phase])
            else:
                now = self.phase_elapsed[phase]
            self.phase_label[phase].config(text=self._format(now))

        # 合计
        total = sum(self.phase_elapsed[p] for p in PHASES)
        # 加上当前正在计时的那个
        for p in PHASES:
            if self.phase_running[p]:
                total += self.phase_elapsed[p] + (time.time() - self.phase_start[p])
                break
        self.total_label.config(text=self._format(total))

        self.root.after(1000, self._update_clock)

    # ── 保存 ────────────────────────────────────────
    def _save(self):
        order = self.order_var.get().strip()
        if not order:
            messagebox.showwarning("提示", "请输入订单号再保存。")
            return

        # 检查是否还有正在计时的
        running = [p for p in PHASES if self.phase_running[p]]
        if running:
            messagebox.showwarning("提示", f"「{running[0]}」还在计时，请先停止。")
            return

        os.makedirs(SAVE_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}_{order}.json"
        path = os.path.join(SAVE_DIR, filename)

        data = {
            "订单号": order,
            "日期": today,
            "环节": {},
            "合计秒": sum(self.phase_elapsed[p] for p in PHASES),
            "合计时间": self._format(sum(self.phase_elapsed[p] for p in PHASES)),
        }
        for p in PHASES:
            data["环节"][p] = {
                "秒数": round(self.phase_elapsed[p], 1),
                "时间": self._format(self.phase_elapsed[p]),
            }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("保存成功", f"已保存到：\n{filename}")
            self.status.config(text=f"✅ 已保存 {filename}")
            self._reset()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _reset(self):
        self.order_var.set("")
        for p in PHASES:
            self.phase_elapsed[p] = 0.0
            self.phase_running[p] = False
            self.phase_btn[p].config(text=f"▶ {p}")
        self.order_entry.focus()


# ── 入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = TimeTracker(root)
    root.mainloop()
