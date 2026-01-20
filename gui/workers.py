from PyQt6.QtCore import QObject, pyqtSignal, QThread


class CompareWorker(QObject):
    finished = pyqtSignal(dict, int, dict)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(
        self, comparator, target_path, mode="fast", use_sw=True, sw_expansion=1
    ):
        super().__init__()
        self.comparator = comparator
        self.target_path = target_path
        self.mode = mode
        self.use_sw = use_sw
        self.sw_expansion = sw_expansion

    def run(self):
        try:
            results, total_words, source_stats = self.comparator.compare_document(
                self.target_path,
                mode=self.mode,
                use_sw=self.use_sw,
                sw_expansion=self.sw_expansion,
            )
            self.finished.emit(results, total_words, source_stats)
        except Exception as e:
            self.error.emit(str(e))


class IndexWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, comparator, file_paths):
        super().__init__()
        self.comparator = comparator
        self.file_paths = file_paths

    def run(self):
        try:
            self.comparator.add_references(self.file_paths)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
