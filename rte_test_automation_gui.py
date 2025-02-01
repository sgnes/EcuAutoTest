from itertools import zip_longest
from logging import config
import logging
import sys
import json
import re
import time
import os
import importlib
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem
from PySide6.QtCore import QFile, Slot, QAbstractTableModel
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHeaderView
from PySide6 import QtCore,QtGui
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox
import cantools
from can.interfaces.vector import VectorBus
import can
from jinja2 import Environment, FileSystemLoader
from python_lauterbach import PythonLauterbach
from rte_automation_ui import Ui_MainWindow
from rte_intra_test_main import bsw_intra_rte_interface_test, test_inter_receive_rte_signal, test_inter_send_rte_signal, test_intra_rte_signal
from rte_auotest_generation import gen_rte_test_code_script
from basic_test_case import RteInterConf,RteIntraConf

from rte_inter_test_gen import inter_test_all_conf
from rte_intra_test_gen import intra_test_all_confs


log_config = {
    "version":1,
    "root":{
        "handlers" : ["console", "file"],
        "level": "DEBUG"
    },
    "handlers":{
        "console":{
            "formatter": "std_out",
            "class": "logging.StreamHandler",
            "level": "DEBUG"
        },
        'file': {
                'class': 'logging.FileHandler',
                'filename': 'rte_testing.log',
                'mode': 'w',
                'formatter': 'std_out',
            },
    },
    "formatters":{
        "std_out": {
            "format": "%(asctime)s : %(levelname)s : %(module)s : %(funcName)s : %(lineno)d  Log : %(message)s",
            "datefmt":"%d-%m-%Y %I:%M:%S"
        }
    },
}

about_text = """
This is a tool used for TQ250 to testing the RTE interface for BSW software.
Any question please contact BSW team members, thanks.
"""

class RteTestDataTableModel(QAbstractTableModel):

    def __init__(self, data):
        super(RteTestDataTableModel, self).__init__()
        self._data = data
        self.header_labels = ["Index", "RTE ID", "RTE Signal Name", "CAN Message", "CAN Signal", "Test Result"]
        

    def data(self, index, role):
        if role == Qt.DisplayRole:
            # See below for the nested-list data structure.
            # .row() indexes into the outer list,
            # .column() indexes into the sub-list
            return self._data[index.row()][index.column()]
        if role == Qt.BackgroundRole and index.column() == 5:
        # See below for the data structure.
            if self._data[index.row()][index.column()] == "PASS":
                return QtGui.QColor('Green')
            elif self._data[index.row()][index.column()] == "FAIL":
                return QtGui.QColor('Red')
            else:
                return QtGui.QColor('Yellow')
    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            self._data[index.row()] = value
            self.dataChanged.emit(index, index)  # Emit dataChanged signal
            return True
        return False
    
    def rowCount(self, index):
        # The length of the outer list.
        return len(self._data)

    def columnCount(self, index):
        # The following takes the first sub-list, and returns
        # the length (only works if all rows are an equal length)
        return len(self._data[0])
    
    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.header_labels[section]

class IntraTestWorker(QObject):
    intra_completed = Signal(int)
    intra_result = Signal(tuple)
	
    def __init__(self, main, logger=None):
        super(IntraTestWorker, self).__init__()
        
        self.dbg = None
        self.main = main
        self.logger = main.logger


    def start_intra_test(self, confs):
        if not self.dbg:
            self.dbg = PythonLauterbach(self.main.config_data["trace32_path"],
                                    self.main.config_data["elf_file"],
                                    self.main.config_data["setup_cmm"],
                                    logger=self.main.logger) 
            self.dbg.open()
        time.sleep(1)
        self.dbg.write_variable_value("s_NetMgr_TestControl", 2)
        for conf in confs:
            res = test_intra_rte_signal(self.dbg, conf, self.logger)
            self.intra_result.emit(res)
        self.intra_completed.emit(1)

class InterTestWorker(QObject):
    inter_completed = Signal(int)
    inter_result = Signal(tuple)
	
    def __init__(self, main, logger=None):
        super(InterTestWorker, self).__init__()
        
        self.dbg = None
        self.main = main
        self.can_bus = None
        self.db = None
        self.logger = main.logger
        self.tester = None


    def start_inter_test(self, confs):
        if not self.dbg:
            self.dbg = PythonLauterbach(self.main.config_data["trace32_path"],
                                    self.main.config_data["elf_file"],
                                    self.main.config_data["setup_cmm"],
                                    logger=self.main.logger) 
            self.dbg.open()
        if not self.can_bus:
            self.db = cantools.database.load_file(self.main.config_data["dbc"])
            timing_fd = can.BitTimingFd(f_clock=80000000, nom_brp=1, nom_tseg1=127, nom_tseg2=32, nom_sjw=32, data_brp=1, data_tseg1=27, data_tseg2=12, data_sjw=12)
            #TODO should add logic to handle other devices later
            self.can_bus = can.interface.Bus(bustype='vector',channel='0',fd=True,timing=timing_fd)
            self.tester = cantools.tester.Tester('LE_TWIN', self.db, self.can_bus, 'ACANFD')
        time.sleep(1)
        self.dbg.write_variable_value("s_NetMgr_TestControl", 3)
        for conf in confs:
            if conf.dir == "in":
                res = test_inter_receive_rte_signal(self.db, self.can_bus, self.dbg, conf, self.logger)
            else:
                res = test_inter_send_rte_signal(self.db, self.can_bus, self.dbg, conf, self.tester, self.logger)
            self.inter_result.emit(res)
        self.inter_completed.emit(1)

class MainWindow(QMainWindow):
    intra_test_command = Signal(list)
    inter_test_command = Signal(list)
    tablewidget_index = len("tableWidget_")


    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        config.dictConfig(log_config)
        self.logger = logging.getLogger(__name__)
        self.init_window()
        self.setWindowTitle("TwinDrive TQ25x RTE Test Automation")
        self.config_data = None
        self.config_file = None
        self.intra_model = None
        self.intra_data_ui = []
        self.intra_result_dict = {}
        self.inter_result_dict = {}
        self.inter_model = None
        self.inter_data_ui = []
        self.inter_confs = []
        self.intra_confs = []
        self.intra_worker_inited = False
        self.inter_worker_inited = False
        self.intra_worker = None
        self.intra_worker_thread = None
        self.inter_worker = None
        self.inter_worker_thread = None
        self.intra_test_current_idx = 0
        self.inter_test_current_idx = 0
        self.dbg = None
        self.can_bus = None
        self.lineedit_dict = {"dbc":self.ui.lineEdit_dbc,
                                 "elf_file":self.ui.lineEdit_elf_file, 
                                 "rte_file":self.ui.lineEdit_rte_file,
                                 "rte_gen_folder":self.ui.lineEdit_rte_gen_folder,
                                 "setup_cmm":self.ui.lineEdit_setup_cmm,
                                 "c_source_path":self.ui.lineEdit_c_source_path,
                                 "trace32_path":self.ui.lineEdit_trace32_path}
        self.tablewidget_dict = {"value_map":self.ui.tableWidget_value_map,
                                 "data_map":self.ui.tableWidget_data_types_map, 
                                 "runnable_addition_def":self.ui.tableWidget_runnable_addition_def,
                                 "runnable_map":self.ui.tableWidget_runnable_map,
                                 "runnable_addition_header":self.ui.tableWidget_runnable_addition_header,
                                 "rte_stub_source_addition":self.ui.tableWidget_rte_stub_source_addition}
        self._auto_load_config()

    def _auto_load_config(self):
        if os.path.exists("rte_autotest_conf.json"):
            self._load_configuration("rte_autotest_conf.json")
        if os.path.exists("rte_inter_test_gen.py"):
            self._load_inter_test_case_data()
        if os.path.exists("rte_intra_test_gen.py"):
            self._load_intra_test_case_data()

    def _setup_intra_test_worker(self):
        if not self.intra_worker_inited:
            self.intra_worker_inited = True
            self.intra_worker = IntraTestWorker(self)
            self.intra_worker_thread = QThread()
            self.intra_worker.intra_completed.connect(self.update_intra_test_done)
            self.intra_worker.intra_result.connect(self._update_intra_result_slot)
            self.intra_test_command.connect(self.intra_worker.start_intra_test)
            self.intra_worker.moveToThread(self.intra_worker_thread)
            self.intra_worker_thread.start()

    def _setup_inter_test_worker(self):
        if not self.inter_worker_inited:
            self.inter_worker_inited = True
            self.inter_worker = InterTestWorker(self)
            self.inter_worker_thread = QThread()
            self.inter_worker.inter_completed.connect(self.update_inter_test_done)
            self.inter_worker.inter_result.connect(self._update_inter_result_slot)
            self.inter_test_command.connect(self.inter_worker.start_inter_test)
            self.inter_worker.moveToThread(self.inter_worker_thread)
            self.inter_worker_thread.start()

    def init_window(self):
        self.ui.tableWidget_value_map.resizeColumnsToContents()
        self.ui.tableWidget_data_types_map.resizeColumnsToContents()
        self.ui.tableWidget_runnable_addition_def.resizeColumnsToContents()
        self.ui.tableWidget_runnable_map.resizeColumnsToContents()
        self.ui.tableWidget_runnable_addition_header.resizeColumnsToContents()
        self.ui.tableWidget_rte_stub_source_addition.resizeColumnsToContents()

        self.ui.tableWidget_runnable_map.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget_runnable_addition_header.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget_runnable_addition_def.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget_data_types_map.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget_value_map.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget_rte_stub_source_addition.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableView_intra_test_cases.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableView_intra_test_cases.horizontalHeader().setStretchLastSection(True)
        self.ui.tableView_inter_test_cases.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableView_inter_test_cases.horizontalHeader().setStretchLastSection(True)

        self.ui.pushButton_rte_file.clicked.connect(lambda: self._select_file(self.ui.lineEdit_rte_file, "*.xlsx", self.ui.checkBox_rte_file))
        self.ui.pushButton_c_source_path.clicked.connect(lambda: self._select_folder(self.ui.lineEdit_c_source_path, self.ui.checkBox_c_source_path))
        self.ui.pushButton_rte_gen_folder.clicked.connect(lambda: self._select_folder(self.ui.lineEdit_rte_gen_folder, self.ui.checkBox_rte_gen_folder))
        self.ui.pushButton_dbc_file.clicked.connect(lambda: self._select_file(self.ui.lineEdit_dbc, "*.dbc *.DBC", self.ui.checkBox_dbc_file))
        self.ui.pushButton_elf_file.clicked.connect(lambda: self._select_file(self.ui.lineEdit_elf_file, "*.elf", self.ui.checkBox_elf_file))
        self.ui.pushButton_setup_cmm.clicked.connect(lambda: self._select_file(self.ui.lineEdit_setup_cmm, "*.cmm", self.ui.checkBox_setup_cmm))
        self.ui.pushButton_trace32_path.clicked.connect(lambda: self._select_file(self.ui.lineEdit_trace32_path, "*.exe", self.ui.checkBox_trace32_path))
        self.ui.pushButton_generation.clicked.connect(self._start_generation)
        self.ui.pushButton_load_intra_test_case.clicked.connect(self._load_intra_test_case_data)
        self.ui.pushButton_start_intra_test.clicked.connect(lambda:self._start_intra_test(test_case_id=None))
        self.ui.pushButton_load_inter_test_case.clicked.connect(self._load_inter_test_case_data)
        self.ui.pushButton_start_inter_test.clicked.connect(self._start_inter_test)
        self.ui.comboBox_can_device.currentIndexChanged.connect(self._update_can_device_select)
        self.ui.pushButton_gen_inter_report.clicked.connect(self.gen_inter_report)
        self.ui.pushButton_gen_intra_report.clicked.connect(self.gen_intra_report)


        self._setup_table_menu(self.ui.tableWidget_runnable_map)
        self._setup_table_menu(self.ui.tableWidget_value_map)
        self._setup_table_menu(self.ui.tableWidget_data_types_map)
        self._setup_table_menu(self.ui.tableWidget_runnable_addition_def)
        self._setup_table_menu(self.ui.tableWidget_runnable_addition_header)
        self._setup_table_menu(self.ui.tableWidget_rte_stub_source_addition)
        self._setup_test_view_menu(self.ui.tableView_intra_test_cases, self._intra_test_signle)
        self._setup_test_view_menu(self.ui.tableView_inter_test_cases, self._inter_test_signle)

        self.ui.actionLoad_Configuration.triggered.connect(self._select_load_configuration)
        self.ui.actionSave_Configuration.triggered.connect(self._save_current_configuration)
        self.ui.actionAbout.triggered.connect(self._show_about_infor)
        self.ui.actionUser_Manual.triggered.connect(self._show_user_manual)
                
        self.ui.tableWidget_runnable_map.itemChanged.connect(lambda : self._save_data_to_config(self.ui.tableWidget_runnable_map))
        self.ui.tableWidget_value_map.itemChanged.connect(lambda: self._save_data_to_config(self.ui.tableWidget_value_map))
        self.ui.tableWidget_data_types_map.itemChanged.connect(lambda: self._save_data_to_config(self.ui.tableWidget_data_types_map))
        self.ui.tableWidget_runnable_addition_def.itemChanged.connect(lambda: self._save_runnable_addi_data_to_config(self.ui.tableWidget_runnable_addition_def))
        self.ui.tableWidget_runnable_addition_header.itemChanged.connect(lambda: self._save_runnable_addi_data_to_config(self.ui.tableWidget_runnable_addition_header))
        self.ui.tableWidget_rte_stub_source_addition.itemChanged.connect(self._save_rte_stub_table_widget_data)
        self.ui.checkBox_c_source_path.stateChanged.connect(lambda:self._checkbox_changed(self.ui.lineEdit_c_source_path, self.ui.checkBox_c_source_path))
        self.ui.checkBox_dbc_file.stateChanged.connect(lambda:self._checkbox_changed(self.ui.lineEdit_dbc, self.ui.checkBox_dbc_file))
        self.ui.checkBox_elf_file.stateChanged.connect(lambda:self._checkbox_changed(self.ui.lineEdit_elf_file, self.ui.checkBox_elf_file))
        self.ui.checkBox_rte_file.stateChanged.connect(lambda:self._checkbox_changed(self.ui.lineEdit_rte_file, self.ui.checkBox_rte_file))
        self.ui.checkBox_rte_gen_folder.stateChanged.connect(lambda:self._checkbox_changed(self.ui.lineEdit_rte_gen_folder, self.ui.checkBox_rte_gen_folder))

    def _checkbox_changed(self, line_edit, check_box):
        path_ = line_edit.text()
        if check_box.isChecked():
            res = self._abs_path_to_relative_path(path_)
            if res:
                path_ = res
            else:
                check_box.setCheckState(Qt.Unchecked)
        else:
            path_ = os.path.abspath(path_)
        line_edit.setText(path_)
        self.config_data[line_edit.objectName()[9:]] = path_


    def _save_rte_stub_table_widget_data(self):
        self.config_data['rte_stub_source_addition_func'] = []
        table_widget = self.ui.tableWidget_rte_stub_source_addition
        for row in range(table_widget.rowCount()):
            key = table_widget.item(row, 0)
            if key and key.text() and key.text() != "":
                self.config_data['rte_stub_source_addition_func'].append(key.text())
        self.config_data['rte_stub_source_addition_variable'] = []
        for row in range(table_widget.rowCount()):
            key = table_widget.item(row, 1)
            if key and key.text() and key.text() != "":
                self.config_data['rte_stub_source_addition_variable'].append(key.text())
    # Define a slot to save the modified data back to self.config_data
    def _save_data_to_config(self, table_widget):
        mapkey = table_widget.objectName()[MainWindow.tablewidget_index:]
        self.config_data[mapkey] = {}
        for row in range(table_widget.rowCount()):
            key = table_widget.item(row, 0)
            value = table_widget.item(row, 1)
            if key and value:
                self.config_data[mapkey][key.text()] = value.text()
        pass
        # Add similar conditions for other table widgets

    def _save_runnable_addi_data_to_config(self, table_widget):
        mapkey = table_widget.objectName()[MainWindow.tablewidget_index:]
        self.config_data[mapkey] = {}
        for row in range(table_widget.rowCount()):
            key = table_widget.item(row, 0)
            value = table_widget.item(row, 1)
            if key and value:
                if key.text() not in self.config_data[mapkey]:
                    self.config_data[mapkey][key.text()] = []
                self.config_data[mapkey][key.text()].append(value.text())

    def _update_can_device_select(self, index):
        self.config_data["can_device"] = index

    def gen_inter_report(self):
        _datatime = time.strftime("%Y-%m-%d-%H_%M_%S",time.localtime(time.time()))
        report_file_name = f"bsw_rte_inter_test_report_{_datatime}.html"
        test_res = []
        for _, res in self.inter_result_dict:
            test_res.append(res)
        env = Environment(loader=FileSystemLoader('./'))
        template = env.get_template('rte_test_report_temp.html')
        with open(report_file_name, 'w+', encoding='utf-8') as f:
            out = template.render(TestResults=test_res)
            f.write(out)
            f.close()
        os.system(report_file_name)

    def gen_intra_report(self):
        _datatime = time.strftime("%Y-%m-%d-%H_%M_%S",time.localtime(time.time()))
        report_file_name = f"bsw_rte_intra_test_report_{_datatime}.html"
        test_res = []
        for _, res in self.intra_result_dict:
            test_res.append(res)
        env = Environment(loader=FileSystemLoader('./'))
        template = env.get_template('rte_test_report_temp.html')
        with open(report_file_name, 'w+', encoding='utf-8') as f:
            out = template.render(TestResults=test_res)
            f.write(out)
            f.close()
        os.system(report_file_name)

    def _load_intra_test_case_data(self):
        #importlib.reload(intra_test_all_confs)
        self.intra_data_ui = []
        self.intra_confs = intra_test_all_confs
        re_exp = r"[Intrae\s]+\s+Test\s+Case\s+(\d+)\s+RTE\sID:\s+([\d\.a-zA-Z_]+)\sName:([\d\.a-zA-Z_]+)\sCAN\sMessage:(.*?)\sSignal:(.*)"
        for conf in intra_test_all_confs:
            res = re.findall(re_exp, conf.title)
            self.intra_data_ui.append(list(res[0]) + ["Not Tested"])
        self.intra_model = RteTestDataTableModel(self.intra_data_ui)
        self.ui.tableView_intra_test_cases.setModel(self.intra_model)
        self.ui.tableView_intra_test_cases.model().dataChanged.connect(self.ui.tableView_intra_test_cases.viewport().update)

    def _start_intra_test(self, test_case_id=None):
        self.ui.pushButton_start_intra_test.setText("Stop Testing")
        self.ui.pushButton_start_intra_test.setStyleSheet("background-color: red")
        self._setup_intra_test_worker()
        if test_case_id != None:
            self.init_intra_number(1)
            self.intra_test_command.emit([self.intra_confs[test_case_id]])
        else:
            self.init_intra_number(len(self.intra_confs))
            self.intra_test_command.emit(self.intra_confs)
        

    @QtCore.Slot(int)
    def init_intra_number(self, n):
        self.intra_test_current_idx = 0
        self.ui.progressBar_intra_test.setMaximum(n)
        self.ui.progressBar_intra_test.setValue(0)

    @QtCore.Slot(int)
    def init_inter_number(self, n):
        self.inter_test_current_idx = 0
        self.ui.progressBar_inter_test.setMaximum(n)
        self.ui.progressBar_inter_test.setValue(0)

    def update_intra_test_done(self):
        pass

    def update_inter_test_done(self):
        pass

    def _load_inter_test_case_data(self):
        self.inter_data_ui = []
        re_exp = r"[Intrae\s]+\s+Test\s+Case\s+(\d+)\s+RTE\sID:\s+([\d\.a-zA-Z_]+)\sName:([\d\.a-zA-Z_]+)\sCAN\sMessage:(.*?)\sSignal:(.*)"
        for conf in inter_test_all_conf:
            res = re.findall(re_exp, conf.title)
            self.inter_data_ui.append(list(res[0]) + ["Not Tested"])
        self.inter_model = RteTestDataTableModel(self.inter_data_ui)
        self.ui.tableView_inter_test_cases.setModel(self.inter_model)
        self.ui.tableView_inter_test_cases.model().dataChanged.connect(self.ui.tableView_inter_test_cases.viewport().update)

    def _start_inter_test(self, test_case_id=None):
        self._setup_inter_test_worker()
        if test_case_id is not None:
            self.init_inter_number(1)
            self.inter_test_command.emit([self.inter_confs[test_case_id]])
        else:
            self.init_inter_number(len(self.inter_confs))
            self.inter_test_command.emit(self.inter_confs)

    @QtCore.Slot(tuple)
    def _update_intra_result_slot(self, res):
        self.intra_test_current_idx += 1
        self.intra_data_ui[res.id][5] = res.OverAllRes
        self.ui.tableView_intra_test_cases.viewport().update()
        self.ui.progressBar_intra_test.setValue(self.intra_test_current_idx)
        self.intra_result_dict[res.TestCaseTitle] = res
 
    @QtCore.Slot(tuple)
    def _update_inter_result_slot(self, res):
        self.inter_test_current_idx += 1
        self.inter_data_ui[res.id][5] = res.OverAllRes
        self.ui.tableView_inter_test_cases.viewport().update()
        self.ui.progressBar_inter_test.setValue(self.inter_test_current_idx)
        self.inter_result_dict[res.TestCaseTitle] = res.inter_data_ui[res[0]][5] = res[1]
        self.ui.tableView_inter_test_cases.viewport().update()

    def _show_user_manual(self):
        pass
    def _show_about_infor(self):
        QMessageBox.information(None, "About", about_text)


    def _save_current_configuration(self):
        with open(self.config_file,"w", encoding='utf-8') as f: ## 设置'utf-8'编码
            f.write(json.dumps(self.config_data, ensure_ascii=False, indent=4)) 

    def _select_load_configuration(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open Configuration File", "", "JSON Files (*.json)")
        if file_path:
            self._load_configuration(file_path)

    def _load_configuration(self, file_path):
        self.config_file = file_path
        with open(file_path, 'r', encoding="utf-8") as file:
            self.config_data = json.load(file)
            self.ui.tableWidget_runnable_map.clearContents()
            self.ui.tableWidget_runnable_map.setRowCount(0)
            for runnable_rte, runnable_code in self.config_data['runnable_map'].items():
                self._add_new_row_with_data(self.ui.tableWidget_runnable_map, [runnable_rte, runnable_code])
            self.ui.tableWidget_value_map.clearContents()
            self.ui.tableWidget_value_map.setRowCount(0)
            for value_rte, value_code in self.config_data['value_map'].items():
                self._add_new_row_with_data(self.ui.tableWidget_value_map, [value_rte, value_code])
            self.ui.tableWidget_data_types_map.clearContents()
            self.ui.tableWidget_data_types_map.setRowCount(0)
            for type_rte, type_code in self.config_data['data_types_map'].items():
                self._add_new_row_with_data(self.ui.tableWidget_data_types_map, [type_rte, type_code])
            self.ui.tableWidget_rte_stub_source_addition.clearContents()
            self.ui.tableWidget_rte_stub_source_addition.setRowCount(0)
            funcs = self.config_data['rte_stub_source_addition_func']
            vars_ = self.config_data['rte_stub_source_addition_variable']
            funcs_aligned, vars_aligned = zip(*zip_longest(funcs, vars_, fillvalue=""))
            for i in range(0, len(funcs_aligned), 1):
                self._add_new_row_with_data(self.ui.tableWidget_rte_stub_source_addition, [funcs_aligned[i], vars_aligned[i]])
            self.ui.tableWidget_runnable_addition_def.clearContents()
            self.ui.tableWidget_runnable_addition_def.setRowCount(0)
            for key, value in self.config_data['runnable_addition_def'].items():
                for func in value:
                    self._add_new_row_with_data(self.ui.tableWidget_runnable_addition_def, [key, func])
            self.ui.tableWidget_runnable_addition_header.clearContents()
            self.ui.tableWidget_runnable_addition_header.setRowCount(0)
            for key, value in self.config_data['runnable_addition_header'].items():
                for header in value:
                    self._add_new_row_with_data(self.ui.tableWidget_runnable_addition_header, [key, header])
            
            for key, lineedit in self.lineedit_dict.items():
                lineedit.setText(self.config_data[key] if key in self.config_data else "")

            index_ = int(self.config_data["can_device"]) if "can_device" in self.config_data else 0
            self.ui.comboBox_can_device.setCurrentIndex(index_)


            

    def _setup_table_menu(self, table_widget):
        context_menu = QMenu(table_widget)
        add_row_action = QAction("Add a new row", table_widget)
        delete_row_action = QAction("Delete this row", table_widget)
        add_row_action.triggered.connect(lambda: self._add_new_row(table_widget))
        delete_row_action.triggered.connect(lambda: self._delete_current_row(table_widget))
        context_menu.addAction(add_row_action)
        context_menu.addAction(delete_row_action)
        table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        table_widget.customContextMenuRequested.connect(lambda pos: context_menu.exec(table_widget.mapToGlobal(pos)))
    
    def _setup_test_view_menu(self, table_widget, action_slot):
        context_menu = QMenu(table_widget)
        test_single_action = QAction("Test This One", table_widget)
        test_single_action.triggered.connect(lambda: action_slot(table_widget))
        context_menu.addAction(test_single_action)
        table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        table_widget.customContextMenuRequested.connect(lambda pos: context_menu.exec(table_widget.mapToGlobal(pos)))

    def _delete_current_row(self, table_widget):
        row = table_widget.currentRow()
        table_widget.removeRow(row)
        if table_widget.objectName() == 'tableWidget_rte_stub_source_addition':
            self._save_rte_stub_table_widget_data()
        elif table_widget.objectName() in ['tableWidget_runnable_addition_header', "tableWidget_runnable_addition_def"]:
            self._save_runnable_addi_data_to_config(table_widget)
        else:
            self._save_data_to_config(table_widget)

    def _intra_test_signle(self, table_widget):
        row = table_widget.currentIndex().row()        #获取被选择的行数
        pass

        self._start_intra_test(test_case_id=row)

    def _inter_test_signle(self, table_widget):
        row = table_widget.currentIndex().row()        #获取被选择的行数
        pass

        self._start_inter_test(test_case_id=row)

    def _add_new_row(self, table_widget):
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        item = QTableWidgetItem(str(""))
        table_widget.setItem(row, 1, item)

    def _add_new_row_with_data(self, table_widget, data):
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        col = 0
        for value in data:
            value = " , ".join(value) if type(value) == list else str(value)
            item = QTableWidgetItem(value)
            table_widget.setItem(row, col, item)
            col += 1

    def _abs_path_to_relative_path(self, path_):
        if os.path.splitdrive(path_)[0] == os.path.splitdrive(os.getcwd())[0]:
            path_ = os.path.relpath(path_, start=os.getcwd())
            return path_
        else:
            QMessageBox.warning(None, "Warnning", "With the relative path checkbox selected, but you selected a different drive, will use absolute path instead.")
            return None
    

    def _select_folder(self, line_edit, check_box):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder_path:
            if check_box.isChecked():
                res = self._abs_path_to_relative_path(folder_path)
                if res:
                    folder_path = res
                else:
                    check_box.setCheckState(Qt.Unchecked)

            line_edit.setText(folder_path)
            self.config_data[line_edit.objectName()[9:]] = folder_path
    
    def _select_file(self, line_edit, ext, check_box):
        file_path,_ = QFileDialog.getOpenFileName(
        self,  # 父窗口对象
        "Please Select File",  # 标题
        r".",  # 起始目录
        f"File Extension ({ext})"  # 选择类型过滤项，过滤内容在括号中
        )
        if file_path:
            if check_box.isChecked():
                res = self._abs_path_to_relative_path(file_path)
                if res:
                    file_path = res
                else:
                    check_box.setCheckState(Qt.Unchecked)
            line_edit.setText(file_path)
            self.config_data[line_edit.objectName()[9:]] = file_path
    
    def _start_generation(self):
        self.ui.pushButton_generation.setEnabled(0)
        gen_rte_test_code_script(data_base=self.config_data["dbc"], rte_file=self.config_data["rte_file"], gen_path=self.config_data["rte_gen_folder"], gen_conf=self.config_file)
        self.ui.pushButton_generation.setEnabled(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())