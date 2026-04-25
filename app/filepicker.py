import flet as ft


class FilePickerService:

    def __init__(self):

        self.picker = ft.FilePicker()

        self.on_result_callback = None
        self.on_upload_callback = None

        self.picker.on_result = self._handle_result
        self.picker.on_upload = self._handle_upload

    # ======================================================
    # REGISTRO GLOBAL (OBRIGATÓRIO FLET 0.80+)
    # ======================================================
    def register(self, page: ft.Page):

        # evita duplicar
        if hasattr(page, "file_picker_service"):
            return page.file_picker_service

        print("✅ Registrando FilePickerService")

        page.services.append(self.picker)

        # ⭐ referência global
        page.file_picker_service = self

        # ⭐ garante sincronização frontend
        page.update()

        return self

    # ======================================================
    # BRIDGE EVENTS
    # ======================================================
    def _handle_result(self, e):

        print("📂 RESULT:", e.files)

        if self.on_result_callback:
            self.on_result_callback(e)

    def _handle_upload(self, e):

        if self.on_upload_callback:
            self.on_upload_callback(e)

    # ======================================================
    # API PÚBLICA
    # ======================================================
    async def pick_files(self, **kwargs):
        result = await self.picker.pick_files(**kwargs)
        print(f"🔥 RAW RESULT TYPE: {type(result)}")
        print(f"🔥 RAW RESULT: {result}")
        if result and self.on_result_callback:
            class FakeEvent:
                pass
            fake = FakeEvent()
            if hasattr(result, 'files'):
                fake.files = result.files
            else:
                fake.files = result
            self.on_result_callback(fake)
        return result

    def upload(self, files):
        self.picker.upload(files)

    async def upload_async(self, files):
        self.picker.upload(files)