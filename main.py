"""
E-Tracker — Flet edition
A mobile-friendly expense tracker with configurable budgets and persistent local storage.

Features:
- Add expenses by category (food, transport, bills, others)
- View, select, and delete expenses
- Total spending and category summaries
- KES currency
- User-configurable budget amount and custom period (start/end dates)
- Alerts when approaching or exceeding the budget
- Stores expenses and settings in a local JSON file
"""
import json
import os
from datetime import date, datetime, timedelta

import flet as ft


APP_TITLE = "E-Tracker"
CATEGORIES = ("food", "transport", "bills", "others")
DEFAULT_BUDGET = 5000.0
ALERT_APPROACHING_RATIO = 0.80


def money(value: float) -> str:
    return f"KES {value:,.2f}"


def parse_date(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


class ETracker:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = APP_TITLE
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = "#10131A"
        self.page.padding = 16
        self.page.spacing = 12
        self.page.window_min_width = 360
        self.page.window_min_height = 650
        self.page.scroll = ft.ScrollMode.AUTO

        # client_storage is persistent app/browser storage; use it for portability across
        # desktop and mobile, avoiding platform-specific filesystem paths.
        self.expenses = []
        self.settings = {
            "budget_amount": DEFAULT_BUDGET,
            "budget_start": date.today().replace(day=1).isoformat(),
            "budget_end": (date.today().replace(day=1) + timedelta(days=31)).replace(day=1).isoformat(),
            "approaching_percent": 80,
        }
        self.selected_id = None
        self._load_data()

        self.budget_amount_input = ft.TextField(
            label="Budget amount (KES)", value=str(self.settings["budget_amount"]),
            keyboard_type=ft.KeyboardType.NUMBER, dense=True, expand=True,
        )
        self.budget_start_input = ft.TextField(
            label="Period start (YYYY-MM-DD)", value=self.settings["budget_start"],
            hint_text="2026-10-01", dense=True, expand=True,
        )
        self.budget_end_input = ft.TextField(
            label="Period end (YYYY-MM-DD)", value=self.settings["budget_end"],
            hint_text="2026-10-31", dense=True, expand=True,
        )
        self.approaching_input = ft.Dropdown(
            label="Approaching alert",
            value=str(self.settings.get("approaching_percent", 80)),
            options=[
                ft.dropdown.Option("60", "At 60% spent"),
                ft.dropdown.Option("70", "At 70% spent"),
                ft.dropdown.Option("80", "At 80% spent"),
                ft.dropdown.Option("90", "At 90% spent"),
                ft.dropdown.Option("95", "At 95% spent"),
            ],
            dense=True, expand=True,
        )

        self.category_input = ft.Dropdown(
            label="Category", value="food",
            options=[ft.dropdown.Option(c, c.title()) for c in CATEGORIES],
            dense=True, expand=True,
        )
        self.amount_input = ft.TextField(
            label="Amount (KES)", hint_text="e.g. 250.00",
            keyboard_type=ft.KeyboardType.NUMBER, dense=True, expand=True,
            on_submit=self.add_expense,
        )
        self.note_input = ft.TextField(
            label="Note (optional)", hint_text="What was it for?",
            dense=True, expand=True, on_submit=self.add_expense,
        )

        self.total_value = ft.Text("KES 0.00", size=20, weight=ft.FontWeight.BOLD)
        self.count_value = ft.Text("0", size=20, weight=ft.FontWeight.BOLD)
        self.budget_status_value = ft.Text("Within budget", size=16, weight=ft.FontWeight.BOLD)
        self.budget_detail = ft.Text("", size=13, color="#AAB4C5")
        self.budget_progress = ft.ProgressBar(value=0, color="#64B5F6", bgcolor="#303849")
        self.alert_text = ft.Text("", size=13, weight=ft.FontWeight.BOLD)
        self.records_list = ft.Column(spacing=8)
        self.category_summary = ft.Column(spacing=8)
        self.status_text = ft.Text("Ready", size=12, color="#AAB4C5")

        self.page.add(self.build_ui())
        self.refresh_all()

    def _load_data(self):
        # Flet client storage is available after the page is connected. Use local
        # JSON file persistence in Flet's app data directory where supported.
        try:
            data = self.page.client_storage.get("e_tracker_data")
            if isinstance(data, dict):
                raw_expenses = data.get("expenses", [])
                if isinstance(raw_expenses, list):
                    self.expenses = [
                        x for x in raw_expenses
                        if isinstance(x, dict)
                        and x.get("category") in CATEGORIES
                        and isinstance(x.get("amount"), (int, float))
                        and float(x.get("amount", -1)) >= 0
                    ]
                raw_settings = data.get("settings", {})
                if isinstance(raw_settings, dict):
                    self.settings.update(raw_settings)
        except Exception:
            # First launch or unavailable storage: start with default data.
            self.expenses = []

    def save_data(self):
        payload = {"expenses": self.expenses, "settings": self.settings}
        try:
            self.page.client_storage.set("e_tracker_data", payload)
        except Exception as exc:
            self.notify(f"Could not save data: {exc}", error=True)

    def notify(self, message: str, error: bool = False):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="#9D343B" if error else "#285B88",
        )
        self.page.snack_bar.open = True
        self.page.update()

    def card(self, title: str, content: ft.Control):
        return ft.Container(
            content=ft.Column(
                [ft.Text(title, size=11, color="#AAB4C5", weight=ft.FontWeight.BOLD), content],
                spacing=6,
            ),
            bgcolor="#171C26", padding=14, border_radius=12,
            expand=True,
        )

    def build_ui(self):
        header = ft.Column(
            [
                ft.Text("E-TRACKER", size=27, weight=ft.FontWeight.BOLD, color="#64B5F6"),
                ft.Text("Personal finance dashboard · Kenyan shillings (KES)", size=13, color="#AAB4C5"),
            ],
            spacing=2,
        )

        stats = ft.ResponsiveRow(
            [
                ft.Container(self.card("TOTAL SPENT IN PERIOD", self.total_value), col={"xs": 12, "sm": 6, "md": 4}),
                ft.Container(self.card("TRANSACTIONS IN PERIOD", self.count_value), col={"xs": 6, "sm": 6, "md": 4}),
                ft.Container(self.card("BUDGET STATUS", self.budget_status_value), col={"xs": 6, "sm": 12, "md": 4}),
            ],
            spacing=8, run_spacing=8,
        )

        budget_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Budget settings", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("Choose any amount and date range. Only expenses dated inside this period count toward this budget.",
                            size=12, color="#AAB4C5"),
                    ft.ResponsiveRow([
                        ft.Container(self.budget_amount_input, col={"xs": 12, "sm": 4}),
                        ft.Container(self.budget_start_input, col={"xs": 12, "sm": 4}),
                        ft.Container(self.budget_end_input, col={"xs": 12, "sm": 4}),
                        ft.Container(self.approaching_input, col={"xs": 12, "sm": 6}),
                        ft.Container(
                            ft.ElevatedButton(
                                "Save budget settings", icon=ft.Icons.SAVE,
                                on_click=self.save_budget_settings,
                                style=ft.ButtonStyle(bgcolor="#285B88", color="#FFFFFF"),
                            ),
                            col={"xs": 12, "sm": 6},
                            alignment=ft.alignment.center_left,
                        ),
                    ], spacing=8, run_spacing=8),
                    self.budget_detail,
                    self.budget_progress,
                    self.alert_text,
                ],
                spacing=10,
            ),
            bgcolor="#171C26", padding=16, border_radius=14,
        )

        expense_form = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Add a new expense", size=18, weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow([
                        ft.Container(self.category_input, col={"xs": 12, "sm": 4}),
                        ft.Container(self.amount_input, col={"xs": 12, "sm": 4}),
                        ft.Container(self.note_input, col={"xs": 12, "sm": 4}),
                    ], spacing=8, run_spacing=8),
                    ft.ElevatedButton(
                        "＋ Add expense", icon=ft.Icons.ADD,
                        on_click=self.add_expense,
                        style=ft.ButtonStyle(bgcolor="#285B88", color="#FFFFFF"),
                    ),
                ],
                spacing=10,
            ),
            bgcolor="#171C26", padding=16, border_radius=14,
        )

        records_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Expense records", size=18, weight=ft.FontWeight.BOLD, expand=True),
                            ft.OutlinedButton("Category summary", icon=ft.Icons.CATEGORY,
                                              on_click=self.show_categories),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.records_list,
                    ft.Row([
                        ft.OutlinedButton("Delete selected", icon=ft.Icons.DELETE,
                                           on_click=self.delete_selected),
                        ft.TextButton("Clear selection", on_click=self.clear_selection),
                    ], wrap=True),
                ],
                spacing=12,
            ),
            bgcolor="#171C26", padding=16, border_radius=14,
        )

        return ft.Column(
            [header, stats, budget_section, expense_form, records_section, self.status_text],
            spacing=14,
            expand=True,
        )

    def period_dates(self):
        start = parse_date(self.settings.get("budget_start"), date.today().replace(day=1))
        end = parse_date(self.settings.get("budget_end"), date.today())
        return start, end

    def in_budget_period(self, item):
        start, end = self.period_dates()
        try:
            expense_day = datetime.strptime(item.get("date", "")[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False
        return start <= expense_day <= end

    def period_expenses(self):
        return [item for item in self.expenses if self.in_budget_period(item)]

    def save_budget_settings(self, _event=None):
        raw_amount = (self.budget_amount_input.value or "").strip().replace(",", "")
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.notify("Enter a budget amount greater than zero.", error=True)
            return

        start_text = (self.budget_start_input.value or "").strip()
        end_text = (self.budget_end_input.value or "").strip()
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except ValueError:
            self.notify("Use dates in YYYY-MM-DD format, for example 2026-10-01.", error=True)
            return
        if end < start:
            self.notify("The period end date must be on or after the start date.", error=True)
            return

        try:
            percent = int(self.approaching_input.value or 80)
        except (TypeError, ValueError):
            percent = 80

        self.settings.update({
            "budget_amount": round(amount, 2),
            "budget_start": start.isoformat(),
            "budget_end": end.isoformat(),
            "approaching_percent": percent,
        })
        self.save_data()
        self.refresh_all()
        self.status_text.value = "Budget settings saved."
        self.page.update()
        self.notify("Budget settings saved.")

    def add_expense(self, _event=None):
        category = (self.category_input.value or "food").strip().lower()
        raw = (self.amount_input.value or "").strip().replace(",", "")
        note = (self.note_input.value or "").strip()

        if category not in CATEGORIES:
            self.notify("Choose a valid category.", error=True)
            return
        try:
            amount = float(raw)
            if amount < 0:
                raise ValueError
        except ValueError:
            self.notify("Enter a valid non-negative amount.", error=True)
            return

        self.expenses.append({
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "category": category,
            "amount": round(amount, 2),
            "note": note,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self.save_data()
        self.amount_input.value = ""
        self.note_input.value = ""
        self.selected_id = None
        self.refresh_all()
        self.status_text.value = f"Added {category} expense: {money(amount)}"
        self.page.update()

    def clear_selection(self, _event=None):
        self.selected_id = None
        self.refresh_all()

    def select_expense(self, expense_id):
        self.selected_id = expense_id
        self.refresh_all()

    def delete_selected(self, _event=None):
        if self.selected_id is None:
            self.notify("Select an expense record first.", error=True)
            return
        item = next((x for x in self.expenses if x.get("id") == self.selected_id), None)
        if item is None:
            self.selected_id = None
            self.refresh_all()
            return

        def confirm_delete(_):
            self.expenses = [x for x in self.expenses if x.get("id") != self.selected_id]
            self.selected_id = None
            self.save_data()
            dialog.open = False
            self.page.update()
            self.refresh_all()
            self.notify("Expense deleted.")

        def cancel_delete(_):
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete expense?"),
            content=ft.Text(f"Delete {item['category'].title()} — {money(float(item['amount']))}?"),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_delete),
                ft.TextButton("Delete", on_click=confirm_delete),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def refresh_all(self):
        period_items = self.period_expenses()
        total = sum(float(x["amount"]) for x in period_items)
        budget = float(self.settings.get("budget_amount", DEFAULT_BUDGET))
        percent = int(self.settings.get("approaching_percent", 80))
        ratio = total / budget if budget > 0 else 0

        self.total_value.value = money(total)
        self.count_value.value = str(len(period_items))
        self.budget_progress.value = min(ratio, 1.0)
        self.budget_detail.value = (
            f"Period: {self.settings.get('budget_start')} to {self.settings.get('budget_end')}  ·  "
            f"Spent: {money(total)}  ·  Remaining: {money(budget - total)}"
        )

        if total > budget:
            self.budget_status_value.value = "OVER BUDGET"
            self.budget_status_value.color = "#FF7777"
            self.budget_progress.color = "#FF5555"
            self.alert_text.value = f"⚠ Budget exceeded by {money(total - budget)}."
            self.alert_text.color = "#FF7777"
        elif ratio >= percent / 100:
            self.budget_status_value.value = "NEAR LIMIT"
            self.budget_status_value.color = "#FFC857"
            self.budget_progress.color = "#FFC857"
            self.alert_text.value = f"⚠ You have used {ratio:.0%} of your budget."
            self.alert_text.color = "#FFC857"
        else:
            self.budget_status_value.value = "WITHIN BUDGET"
            self.budget_status_value.color = "#70D6A0"
            self.budget_progress.color = "#64B5F6"
            self.alert_text.value = f"Budget is healthy. {money(max(budget - total, 0))} remaining."
            self.alert_text.color = "#70D6A0"

        self.records_list.controls.clear()
        if not self.expenses:
            self.records_list.controls.append(
                ft.Text("No expenses recorded yet. Add your first expense above.",
                        size=13, color="#AAB4C5")
            )
        else:
            # Newest records first. All records are shown; the budget cards count
            # only records that fall within the selected date range.
            for index, item in reversed(list(enumerate(self.expenses))):
                expense_id = item.setdefault(
                    "id", f"legacy-{index}-{item.get('date', '')}-{item.get('amount', 0)}"
                )
                selected = expense_id == self.selected_id
                line = ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(f"{item['category'].title()} · {money(float(item['amount']))}",
                                            weight=ft.FontWeight.BOLD, color="#64B5F6" if selected else "#F3F6FB"),
                                    ft.Text(f"{item.get('note') or 'No note'} · {item.get('date', '')}",
                                            size=12, color="#AAB4C5"),
                                ],
                                spacing=3, expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                tooltip="Select expense",
                                on_click=lambda e, eid=expense_id: self.select_expense(eid),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    bgcolor="#202735" if selected else "#141923",
                    padding=10, border_radius=9,
                    border=ft.border.all(1, "#285B88" if selected else "#293142"),
                )
                self.records_list.controls.append(line)

        self.category_summary.controls.clear()
        self.page.update()

    def show_categories(self, _event=None):
        period_items = self.period_expenses()
        totals = {category: 0.0 for category in CATEGORIES}
        counts = {category: 0 for category in CATEGORIES}
        for item in period_items:
            category = item["category"]
            totals[category] += float(item["amount"])
            counts[category] += 1

        body = ft.Column(
            [
                ft.Text(f"Budget period: {self.settings['budget_start']} to {self.settings['budget_end']}",
                        size=12, color="#AAB4C5"),
                *[
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(f"{category.title()} · {counts[category]} transaction(s)", expand=True),
                                ft.Text(money(totals[category]), weight=ft.FontWeight.BOLD),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        bgcolor="#202735", padding=12, border_radius=8,
                    )
                    for category in CATEGORIES
                ],
                ft.Divider(),
                ft.Text(f"TOTAL {money(sum(totals.values()))}", size=18,
                        weight=ft.FontWeight.BOLD, color="#64B5F6"),
            ],
            tight=True, spacing=8, scroll=ft.ScrollMode.AUTO,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Category summary"),
            content=ft.Container(body, width=440, height=330),
            actions=[ft.TextButton("Close", on_click=lambda e: self.close_dialog(dialog))],
        )
        self.page.show_dialog(dialog)

    def close_dialog(self, dialog):
        dialog.open = False
        self.page.update()


def main(page: ft.Page):
    ETracker(page)


if __name__ == "__main__":
    ft.app(target=main)
