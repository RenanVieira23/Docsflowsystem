import flet as ft


class FilePickerService:
    def __init__(self):
        self.on_result_callback = None
        self.on_upload_callback = None
        self._page = None

    def register(self, page):
        if hasattr(page, "file_picker_service"):
            return page.file_picker_service
        self._page = page
        page.file_picker_service = self
        return self

    async def pick_files(self, **kwargs):
        picker = ft.FilePicker()
        self._page.services.append(picker)
        self._page.update()
        result = await picker.pick_files(**kwargs)
        self._page.services.remove(picker)
        self._page.update()
        if result and self.on_result_callback:
            class FakeEvent:
                pass

            fake = FakeEvent()
            fake.files = result if not hasattr(result, "files") else result.files
            self.on_result_callback(fake)
        return result

    def upload(self, files):
        pass
