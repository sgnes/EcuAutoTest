import time
from win32com.client import DispatchEx
import win32com
import re
import os
from uds_proj_config import *
import logging
import sys
import xlrd
import tkinter as tk

CANalyzer = None

class MeasEvents:

    def OnInit(self):
        global  CANalyzer
        CANalyzer.update_capl_funs()


class VectorDevice(object):
    """

    """

    def __init__(self, canalyzer_config_path, canape_config_path,baud_rate, a2l_path, capl_path=None, channel=2, device_type="CCP", logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._capl_funcs = {}
        self._capl_path = capl_path
        if self._capl_path is not None:
            self._capl_names = self._get_capl_fun_names()
        self._CANalyzer = DispatchEx('CANalyzer.Application')
        self._CANalyzer.Open(canalyzer_config_path)
        self._CANalyzer.CAPL.Compile()
        global  CANalyzer
        CANalyzer = self
        event_handler = win32com.client.WithEvents(self._CANalyzer.Measurement, MeasEvents)
        self._CANalyzer.UI.Write.Output('measurement starting...')
        self._CANalyzer.Measurement.Start()
        while (not self._CANalyzer.Measurement.Running):
            time.sleep(1)
        self._CANalyzer.UI.Write.Output('measurement started...')
        self.logger.info("Canalyzer measurement started.")

        # init the CANape
        self._Canape = DispatchEx('CANape.Application')
        self._Canape.Open1(canape_config_path, 1, baud_rate, True)
        self._CanapeDev = self._Canape.Devices.Add(device_type, a2l_path, device_type, channel)
        pass

    def close(self):
        self._Canape.Quit()
        self._CANalyzer.Quit()



    def _get_capl_fun_names(self):
        re_exp = "^(void|int|byte|word|dword|long|int64|qword)\s+([a-zA-Z0-9_]+)\s*\((void|int|byte|word|dword|long|int64|qword|float)\s*"
        names = []
        with open(self._capl_path) as capl:
            text = capl.read()
            res = re.findall(re_exp, text, re.M)
            names = [i[1] for i in res]
            self.logger.debug("CAPL functions:{0}".format(names))
        return names

    def get_capl_names(self):
        return self._capl_names

    def update_capl_funs(self):
        for name in self._capl_names:
            obj = self._CANalyzer.CAPL.GetFunction(name)
            self._capl_funcs[name] = obj

    def get_capl_func(self, name):
        if name in self._capl_funcs:
            return self._capl_funcs[name]
        else:
            return  None

    def ChangeEcuCalib(self, case, *args):
        name = case.ActionPar1
        value = case.ActionPar2 if not str(case.ActionPar2).upper().startswith("0X") else int(case.ActionPar2, 16)
        self._CanapeDev.CalibrationObjects.Add(name)
        calib_obj = self._CanapeDev.CalibrationObjects.Item(name)
        calib_obj.Value = value
        calib_obj.Write()
        case.RealVal = case.TestRes = "PASS"
        self.logger.info(case)
        return case.TestRes

    def GetCanBusSIgnalValue(self, case, *args):
        ch, msg, signal = case.ActionPar1, case.ActionPar2, case.ActionPar3
        res = float(str(self._CANalyzer.Bus.GetSignal(ch, msg, signal)))
        exp, resl = [float(i) for i in [case.ExpectPar1, case.ExpectPar2]]
        case.RealVal = res
        if abs(res - exp) <= resl:
            case.TestRes = "PASS"
        else:
            case.TestRes = "FAIL"
        self.logger.info(case)
        return case.TestRes

    def CallCapl(self, case, *args):
        name, value = case.ActionPar1, case.ActionPar2
        if name in self._capl_funcs:
            func = self._capl_funcs[name]
            if value:
                func.Call(value)
            else:
                func.Call()
                case.RealVal = case.TestRes = "PASS"
        else:
            raise NameError
            case.RealVal = case.TestRes = "FAIL"
            self.logger.error("{} CAPL function:{} not founded.".format(sys._getframe().f_code.co_name, name))
        self.logger.info(case)
        return case.TestRes

    def GetEcuVarValue(self, case, *args):
        name = case.ActionPar1
        self._CanapeDev.CalibrationObjects.Add(name)
        calib_obj = self._CanapeDev.CalibrationObjects.Item(name)
        exp = case.ExpectPar1 if not str(case.ExpectPar1).upper().startswith("0X") else int(case.ExpectPar1, 16)
        resl = float(case.ExpectPar2)
        res = float(calib_obj.Read())
        case.RealVal = res
        if abs(res - exp) <= resl:
            case.TestRes = "PASS"
        else:
            case.TestRes = "FAIL"
        self.logger.info(case)
        return case.TestRes

    def Sleep(self, case, *args):
        time.sleep(int(case.ActionPar1)/1000)
        case.TestRes = "PASS"
        self.logger.info(case)
        return case.TestRes

    def SendDiagcReqToEcu(self, case, *args):
        pass


    def ReConnectCCP(self, case, *args):
        self._CanapeDev.GoOffline()
        try:
            self._CanapeDev.GoOnline(False)
        except:
            time.sleep(10)
            self._CanapeDev.GoOnline(False)
        case.TestRes = "PASS"
        self.logger.info(case)
        return case.TestRes

class TestCase():

    def __init__(self,test_case_id, desc, action, par1, par2, par3, expect, exp1, exp2, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.TestCaseId = test_case_id
        self.Description = desc
        self.Action = action
        self.ActionPar1 = par1
        self.ActionPar2 = par2
        self.ActionPar3 = par3
        self.ExpectPar1 = expect
        self.ExpectPar2 = exp1
        self.ExpectPar3 = exp2
        self.TestRes = "NA"
        self.RealVal = None
        self.logger.info(self)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "TestCaseId:{}, Result:{}, Description:{}, Action:{}, ActionPar1:{}, ActionPar2:{}, ActionPar3:{}, ExpectPar1:{}, ExpectPar2:{}, ExpectPar3:{} RealValue:{}".format(
            self.TestCaseId,
            self.TestRes,
            self.Description,
            self.Action,
            self.ActionPar1,
            self.ActionPar2,
            self.ActionPar3,
            self.ExpectPar1,
            self.ExpectPar2,
            self.ExpectPar3,
            self.RealVal)




class TestConfig():

    def __init__(self,project_name, canalyzer_cfg, capl, canape_cfg, baud_rate, a2l, uds_req_id, uds_reps_id, uds_ch, uds_rate, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.ProjectName = project_name
        self.CanalyzerCfgFile = canalyzer_cfg
        self.CaplFile = capl
        self.CanapeCfgPath = canape_cfg
        self.BaudRate = baud_rate
        self.A2lFile = a2l
        self.UdsReqId = uds_req_id
        self.UdsRepsId = uds_reps_id
        self.UdsCh = int(uds_ch)
        self.UdsBaudRate = int(uds_rate)
        self.logger.info(self)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "TestCaseConfig. ProjectName:{}, CanalyzerConf:{}, CaplFile:{}, CanapeConfig:{}, Baudrate:{}, A2lFile:{}, UdsReqId:{}, UdsRepsId:{}, UdsCh:{}, UdsBaudRate:{}".format(
            self.ProjectName,
            self.CanalyzerCfgFile,
            self.CaplFile,
            self.CanapeCfgPath,
            self.BaudRate,
            self.A2lFile,
            self.UdsReqId,
            self.UdsRepsId,
            self.UdsCh,
            self.UdsBaudRate)


class TestDevice(VectorDevice):
    """

    """

    def __init__(self, test_cfg, request_timeout=1, logger=None):
        canalyzer_config_path, canape_config_path, baud_rate, a2l_path, capl_path = test_cfg.CanalyzerCfgFile, \
                                                                                    test_cfg.CanapeCfgPath, \
                                                                                    test_cfg.BaudRate, \
                                                                                    test_cfg.A2lFile,\
                                                                                    test_cfg.CaplFile
        VectorDevice.__init__(self, canalyzer_config_path, canape_config_path, baud_rate, a2l_path, capl_path, channel=2, device_type="CCP", logger=None)
        self._bus = VectorBus(channel=test_cfg.UdsCh, bitrate=test_cfg.UdsBaudRate)  # Link Layer (CAN protocol)
        self._tp_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=int(test_cfg.UdsReqId, 16),rxid=int(test_cfg.UdsRepsId, 16))  # Network layer addressing scheme
        self._stack = isotp.CanStack(bus=self._bus, address=self._tp_addr,params=isotp_params)  # Network/Transport layer (IsoTP protocol)
        self._conn = PythonIsoTpConnection(self._stack)
        self._client = Client(self._conn,client_config, request_timeout)
        self._wait_timeout = None

    def __enter__(self):
        self._client.open()
        return self

    def __exit__(self, type, value, traceback):
        self._client.close()
        self.close()

    def close(self):
        del self._conn
        del self._stack
        del self._bus
        del self._client
        super(TestDevice, self).close()


    def SendDiagcReqToEcu(self, case, *args):
        res = None
        if case.ActionPar1 in ["clear_dtc", "read_data_by_identifier"]:
            par = int(case.ActionPar2, 16)
            res = getattr(self._client, case.ActionPar1)(par)
        elif case.ActionPar1 in ["change_session", "request_seed"]:
            par = int(case.ActionPar2)
            res = getattr(self._client, case.ActionPar1)(par)
        elif case.ActionPar1 in ["write_data_by_identifier"]:
            did, value = int(case.ActionPar2,16) , case.ActionPar3
            res = getattr(self._client, case.ActionPar1)(did, value)

        # check response
        if case.ExpectPar1 == "CheckNRCOnly":
            code = int(res.code)
            exp_code = int(case.ExpectPar2)
            case.RealVal = code
            if code == exp_code:
                case.TestRes = "PASS"
            else:
                case.TestRes = "FAIL"
        elif case.ExpectPar1 == "CheckResponse":
            data = res.data.hex()
            exp_data, mask = case.ExpectPar2, case.ExpectPar3
            case.RealVal = data
            if len(exp_data) != len(data):
                case.TestRes = "FAIL"
                raise ValueError
            else:
                case.TestRes = self._compare_hex_str(data, exp_data, mask)
        else:
            case.TestRes = "PASS"


        # additional action
        if case.ActionPar1 == "request_seed" and res.code == 0:
            level = int(case.ActionPar2)
            seed = res.data.hex()[2:]
            self.logger.debug("Seed for level:{}, is:{}".format(level, seed))
            key = self._client.config["security_algo"](level, seed)
            self.logger.debug("Key  for level:{}, is:{}".format(level, "".join([hex(i)[2:] for i in key])))
            res = self._client.send_key(level+1, key)
            case.RealVal = res.code

        self.logger.info(case)
        return case.TestRes

    def _compare_hex_str(self, data, exp, mask):
        mask_list = [int(mask[i * 2:(i + 1) * 2], 16) for i in range(int(len(data) / 2))]
        data_list = [int(data[i * 2:(i + 1) * 2], 16) & mask_list[i] for i in range(int(len(data) / 2))]
        exp_data_list = [int(exp[i * 2:(i + 1) * 2], 16) & mask_list[i] for i in range(int(len(data) / 2))]
        if data_list == exp_data_list:
            return "PASS"
        else:
            return "FAIL"


    def _timeoutfunc(self):
        self._w.destroy()
        self._wait_timeout = True


    def _GetInputWitTimeout(self, label='Input dialog box', action="", timeout=5000):
        self._w = tk.Tk()
        entryText = tk.StringVar()
        self._w.title(label)
        W_Input = ''
        self._wFrame = tk.Frame(self._w, background="light yellow", padx=20, pady=20)
        self._wFrame.pack()
        self._wEntryBox = tk.Entry(self._wFrame, background="white", width=100, textvariable=entryText)
        self._wEntryBox.focus_force()
        self._wEntryBox.pack()
        entryText.set(action)

        def fin():
            W_Input = str(self._wEntryBox.get())
            self._w.destroy()

        self._wSubmitButton = tk.Button(self._w, text='OK', command=fin, default='active')
        self._wSubmitButton.pack()



        # --- optionnal extra code in order to have a stroke on "Return" equivalent to a mouse click on the OK button
        def fin_R(event):
            fin()

        self._w.bind("<Return>", fin_R)
        # --- END extra code ---

        self._w.after(timeout, self._timeoutfunc)  # This is the KEY INSTRUCTION that destroys the dialog box after the given timeout in millisecondsd
        self._w.mainloop()

    def PrintAndWiat(self, case, *args):
        """
        this command is designed for some test case need to change some input, like disconnect some load,
        change the battery voltage, since this script is not able to do this.
        this command will output the manually action, and wait the user to finish the action and press any key.
        :param case.ActionPar1: the manually action need to be preformed.
        :param args:
        :return:
        """
        timeout = None
        text = case.ActionPar1
        timeout = int(case.ActionPar2)
        self.logger.info("PrintAndWiat: {0}".format(text))
        self._wait_timeout = None
        self._GetInputWitTimeout("Please note on action need to be done manually.", text, timeout)
        if self._wait_timeout:
            case.TestRes = "FAIL"
        else:
            case.TestRes = "PASS"
        self.logger.info("PrintAndWiat: Kep received")
        self.logger.info(case)
        return "PASS"

def load_test_config(test_config_file):
    logger = logging.getLogger(__name__)
    logger.info("test config file name:{0}".format(test_config_file))
    xl_workbook  = xlrd.open_workbook(test_config_file)
    xl_config_sheet = xl_workbook.sheet_by_name("Config")
    col = xl_config_sheet.col(1)
    project_name, canalyzer_cfg, capl, canape_cfg, baud_rate, a2l, uds_req_id, uds_reps_id, uds_ch, uds_rate, *_ = [i.value for i in col]
    test_cfg = TestConfig(project_name, os.path.abspath(canalyzer_cfg), os.path.abspath(capl), os.path.abspath(canape_cfg), baud_rate, os.path.abspath(a2l), uds_req_id, uds_reps_id, uds_ch, uds_rate)

    test_case_list = []

    for name in [i for i in xl_workbook.sheet_names() if i.startswith("TestCase")]:
        xl_testcase_sheet = xl_workbook.sheet_by_name(name)
        rows = xl_testcase_sheet.nrows
        for i in range(1, rows,1):
            row = xl_testcase_sheet.row(i)
            test_case_id, desc, action, par1, par2, par3, expect, exp1, exp2, *_ = [i.value for i in row]
            if action == "":
                break
            case = TestCase(test_case_id, desc, action, par1, par2, par3, expect, exp1, exp2)
            test_case_list.append(case)
    return (test_cfg, test_case_list)

