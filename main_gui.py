import threading

import flet as ft

import main as engine


GREEN = "#00FF00"
GREEN_DIM = "#38B000"
BLACK = "#000000"
PANEL = "#071007"
PANEL_BG = "#0a140a" # Slightly lighter than pure black for the panel
FONT = "Consolas"


def make_text(text, size=14, color=GREEN, weight=None):
    return ft.Text(
        text,
        size=size,
        color=color,
        font_family=FONT,
        weight=weight,
        selectable=True,
    )


def make_panel(content, expand=False):
    border_side = ft.BorderSide(1, GREEN_DIM)
    return ft.Container(
        content=content,
        bgcolor=PANEL_BG,
        border=ft.Border(
            left=border_side,
            top=border_side,
            right=border_side,
            bottom=border_side,
        ),
        border_radius=8,
        padding=20,
        expand=expand,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=8,
            color="#1138B000", # Subtle green glow
        ),
    )


def main(page: ft.Page):
    page.title = "AISINT"
    page.bgcolor = BLACK
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 24
    page.scroll = ft.ScrollMode.AUTO

    state = {
        "config": None,
        "context": None,
        "question_fields": [],
    }

    # Custom button style for a sharper terminal look
    button_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=4),
        side=ft.BorderSide(1, GREEN_DIM),
        color=GREEN,
    )

    status_text = make_text("Waiting for clues.", color=GREEN_DIM)
    progress_bar = ft.ProgressBar(width=760, color=GREEN, bgcolor=PANEL, visible=False)
    
    activity_log = ft.Column(spacing=6)
    question_area = ft.Column(spacing=12)
    result_area = ft.Column(spacing=14)
    followup_area = ft.Column(spacing=10)

    clues_input = ft.TextField(
        label="Clues",
        hint_text="Name, username, city, school, domain, GitHub, project, anything you know...",
        multiline=True,
        min_lines=6,
        max_lines=10,
        width=760,
        color=GREEN,
        border_color=GREEN,
        focused_border_color=GREEN,
        cursor_color=GREEN,
        text_style=ft.TextStyle(color=GREEN, font_family=FONT),
        label_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
        hint_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
    )

    start_button = ft.ElevatedButton("Start Investigation", style=button_style)
    continue_button = ft.ElevatedButton("Answer Questions", visible=False, style=button_style)
    not_one_button = ft.OutlinedButton("It's not the one I think", visible=False, style=button_style)
    ask_button = ft.ElevatedButton("Ask", style=button_style)

    followup_input = ft.TextField(
        label="Ask more about this person",
        hint_text="Example: what sources support the college claim?",
        width=760,
        color=GREEN,
        border_color=GREEN,
        focused_border_color=GREEN,
        cursor_color=GREEN,
        text_style=ft.TextStyle(color=GREEN, font_family=FONT),
        label_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
        hint_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
        visible=False,
    )

    def update_status(message):
        status_text.value = message
        activity_log.controls.append(make_text(f"> {message}", size=12, color=GREEN_DIM))
        page.update()

    def set_busy(is_busy):
        start_button.disabled = is_busy
        continue_button.disabled = is_busy
        ask_button.disabled = is_busy
        not_one_button.disabled = is_busy
        progress_bar.visible = is_busy
        page.update()

    def show_error(error):
        status_text.value = "Error."
        result_area.controls.append(make_panel(make_text(str(error), color="#FF4D4D")))
        set_busy(False)
        page.update()

    def render_questions(questions):
        question_area.controls.clear()
        state["question_fields"] = []

        if not questions:
            question_area.controls.append(
                make_text("Opus did not need extra questions. Continue to final analysis.")
            )
        else:
            question_area.controls.append(
                make_text(
                    "Opus needs a few clarifications. Answer yes, no, idk, or anything useful.",
                    color=GREEN_DIM,
                )
            )

        for index, question in enumerate(questions, start=1):
            question_text = question.get("question", "")
            why = question.get("why", "")
            answer_input = ft.TextField(
                label=f"Answer {index}",
                hint_text="yes / no / idk / custom answer",
                value="idk",
                width=760,
                color=GREEN,
                border_color=GREEN,
                focused_border_color=GREEN,
                cursor_color=GREEN,
                text_style=ft.TextStyle(color=GREEN, font_family=FONT),
                label_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
                hint_style=ft.TextStyle(color=GREEN_DIM, font_family=FONT),
            )
            state["question_fields"].append((question_text, answer_input))
            question_area.controls.append(
                make_panel(
                    ft.Column(
                        [
                            make_text(f"{index}. {question_text}", weight=ft.FontWeight.BOLD),
                            make_text(f"Why: {why}", size=12, color=GREEN_DIM),
                            answer_input,
                        ],
                        spacing=8,
                    )
                )
            )

        continue_button.visible = True
        page.update()

    def render_final_profile(final_profile):
        selected = final_profile.get("selected_person", {})
        report = final_profile.get("report_markdown", "")
        confidence = selected.get("confidence", "unknown")

        result_area.controls.clear()
        result_area.controls.append(
            make_panel(
                ft.Column(
                    [
                        make_text("Selected Person", size=22, weight=ft.FontWeight.BOLD),
                        make_text(selected.get("name", "Unknown"), size=28, weight=ft.FontWeight.BOLD),
                        make_text(selected.get("headline", ""), color=GREEN_DIM),
                        make_text(f"Confidence: {confidence}", color=GREEN_DIM),
                    ],
                    spacing=6,
                )
            )
        )
        result_area.controls.append(
            make_panel(
                ft.Column(
                    [
                        make_text("Detailed Report", size=18, weight=ft.FontWeight.BOLD),
                        make_text(report or "No report returned.", size=14),
                    ],
                    spacing=10,
                )
            )
        )

        next_questions = selected.get("next_questions", [])
        if next_questions:
            result_area.controls.append(
                make_panel(
                    ft.Column(
                        [make_text("Useful Next Questions", weight=ft.FontWeight.BOLD)]
                        + [make_text(f"- {item}", color=GREEN_DIM) for item in next_questions],
                        spacing=6,
                    )
                )
            )

        followup_input.visible = True
        not_one_button.visible = True
        page.update()

    def run_initial():
        try:
            state["config"] = engine.load_runtime_config()
            context = engine.run_initial_investigation(
                clues_input.value.strip(),
                config=state["config"],
                status_callback=update_status,
            )
            state["context"] = context
            update_status("Questions ready.")
            render_questions(context.get("analysis", {}).get("questions", []))
        except Exception as error:
            show_error(error)
        finally:
            set_busy(False)

    def start_investigation(e):
        clues = clues_input.value.strip()
        if not clues:
            show_error("Add at least one clue first.")
            return

        result_area.controls.clear()
        question_area.controls.clear()
        followup_area.controls.clear()
        activity_log.controls.clear()
        followup_input.visible = False
        continue_button.visible = False
        not_one_button.visible = False
        set_busy(True)
        update_status("Starting investigation...")
        threading.Thread(target=run_initial, daemon=True).start()

    def run_completion():
        try:
            answers = [
                {
                    "question": question,
                    "answer": answer_input.value.strip() or "idk",
                }
                for question, answer_input in state["question_fields"]
            ]
            context = engine.complete_investigation(
                state["context"],
                answers,
                config=state["config"],
                status_callback=update_status,
            )
            state["context"] = context
            update_status("Final selected profile ready.")
            render_final_profile(context.get("final_profile", {}))
        except Exception as error:
            show_error(error)
        finally:
            set_busy(False)

    def continue_investigation(e):
        if not state["context"]:
            show_error("Start an investigation first.")
            return

        set_busy(True)
        continue_button.visible = False
        update_status("Continuing investigation...")
        threading.Thread(target=run_completion, daemon=True).start()

    def render_followup_answer(question, answer):
        followup_area.controls.append(
            make_panel(
                ft.Column(
                    [
                        make_text(f"You: {question}", color=GREEN_DIM),
                        make_text(answer),
                    ],
                    spacing=8,
                )
            )
        )
        page.update()

    def run_followup(question):
        try:
            lowered = question.lower()
            if "not the one" in lowered or "wrong person" in lowered:
                alternative = engine.choose_alternative_person(
                    state["context"],
                    config=state["config"],
                    status_callback=update_status,
                )
                render_final_profile(alternative)
                render_followup_answer(question, "I switched to the next most plausible person from the evidence.")
            else:
                answer = engine.answer_profile_question(
                    state["context"],
                    question,
                    config=state["config"],
                )
                render_followup_answer(question, answer)
        except Exception as error:
            show_error(error)
        finally:
            set_busy(False)

    def ask_followup(e):
        question = followup_input.value.strip()
        if not question:
            return
        followup_input.value = ""
        set_busy(True)
        update_status("Answering follow-up...")
        threading.Thread(target=run_followup, args=(question,), daemon=True).start()

    def choose_another(e):
        if not state["context"]:
            return
        set_busy(True)
        update_status("Looking for the next plausible person...")
        threading.Thread(
            target=run_followup,
            args=("it's not the one i think",),
            daemon=True,
        ).start()

    start_button.on_click = start_investigation
    continue_button.on_click = continue_investigation
    ask_button.on_click = ask_followup
    followup_input.on_submit = ask_followup
    not_one_button.on_click = choose_another

    header = ft.Column(
        [
            make_text("AISINT", size=42, weight=ft.FontWeight.BOLD),
            make_text("AI-powered identity investigation", color=GREEN_DIM),
            ft.Divider(color=GREEN_DIM, height=20),
        ],
        spacing=2,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    controls = ft.Row(
        [start_button, continue_button, not_one_button],
        spacing=12,
        wrap=True,
    )

    page.add(
        ft.Column(
            [
                header,
                make_panel(
                    ft.Column(
                        [
                            make_text("Clues", size=18, weight=ft.FontWeight.BOLD),
                            clues_input,
                            controls,
                        ],
                        spacing=12,
                    )
                ),
                make_panel(
                    ft.Column(
                        [
                            make_text("Status", size=18, weight=ft.FontWeight.BOLD),
                            progress_bar,
                            status_text,
                            activity_log,
                        ],
                        spacing=8,
                    )
                ),
                question_area,
                result_area,
                ft.Row([followup_input, ask_button], spacing=10, wrap=True),
                followup_area,
            ],
            spacing=18,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)