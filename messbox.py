from PyQt6.QtWidgets import QDialog
from UI.Messbox import Ui_Dialog

class Messbox(QDialog, Ui_Dialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog
        self.setupUi(self)
        self.show_text = ""
        self.pushButton.clicked.connect(self.hide_UI)

    def show_message(self,type,message = ""):
        if message == "":
            self.textBrowser.setText(self.show_text)
        else:
            self.textBrowser.setText(message)

        if type == "start":
            self.pushButton.setEnabled(False)
            print("start")
            self.exec()
        elif type == "end":
            print("end")
            self.pushButton.setEnabled(True)
        elif type == "error":
            self.pushButton.setEnabled(True)
            self.exec()


    def hide_UI(self):
        self.show_text = ""
        self.hide()

    def mess_ui_btn_true(self):
        """超时"""
        self.textBrowser.setText("超时")
        self.pushButton.setEnabled(True)