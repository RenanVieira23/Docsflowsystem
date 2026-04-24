import flet as ft

def main(page: ft.Page):
    page.add(ft.Text("Flet funcionando"))

ft.run(main, view=ft.AppView.WEB_BROWSER)