import time
from enum import Enum
from abc import ABCMeta, abstractmethod
import tkinter as tk
from loguru import logger as loguru_logger



class TestResult(Enum):
    """Enum class for Test result

    Args:
        Enum (Enum): 
    """
    PASS = "PASS"
    FAIL = "FAIL"


class EcuTestCase(object):
    """Test case for set variable value.

    Args:
        object (_type_): _description_
    """

    class EcuTestCaseType(Enum):
        """_summary_

        Args:
            Enum (_type_): _description_
        """
        SET_VAR_VALUE = "set_var_value"
        GET_VAR_VALUE = "get_var_value"

    class EcuTestCaseEvaluateMethod(Enum):
        """_summary_

        Args:
            Enum (_type_): _description_
        """
        EQUAL_TO = 0
        IN_RANGE = 1
        MASK = 3
        NOT_EQUAL_TO = 4

    def _get_test_case_type(self, type_str):
        for case_type in EcuTestCase.EcuTestCaseType:
            if case_type.value == type_str:
                return case_type
        raise ValueError(f"invalid type {type_str}")

    def _get_evaluate_method(self, method_str):
        for case_type in EcuTestCase.EcuTestCaseEvaluateMethod:
            if case_type.name == method_str:
                return case_type
        raise ValueError(f"invalid type {method_str}")

    def __init__(self, **args):
        """_summary_

        Args:
            name (str): variable name
            value (str): variable value to be set
        """
        self.name = None
        self.description = None
        self.type = None
        self.set_value = None
        self.expect_value = None
        self.evaluate_method = None
        self.evaluate_value = None
        self.get_value = None
        self.mandatory_attrs = {EcuTestCase.EcuTestCaseType.SET_VAR_VALUE:["name", "description", "type", "set_value"],
                                EcuTestCase.EcuTestCaseType.GET_VAR_VALUE:["name", "description", "type", "expect_value", "evaluate_method","evaluate_value"]}
        if "type" not in args:
            raise KeyError("test case type should not be None")
        
        case_type = self._get_test_case_type(args['type'])
        attrs = self.mandatory_attrs[case_type]
        for attr in attrs:
            if attr not in args:
                raise ValueError(f"Parameter {attr} is mandatory for test case type: {case_type.value}")
        for attr,value in args.items():
            setattr(self, attr, value)
        if case_type is EcuTestCase.EcuTestCaseType.GET_VAR_VALUE:
            self.evaluate_method = self._get_evaluate_method(args["evaluate_method"])
            if self.evaluate_method == EcuTestCase.EcuTestCaseEvaluateMethod.IN_RANGE:
                if not isinstance(self.expect_value, list) or len(self.expect_value) != 2:
                    raise ValueError(f"Parameter evaluate_method with value IN_RANGE, has unexpected expect_value:{self.expect_value}")
        self.type = case_type
        self.result = TestResult.FAIL
        self.timeout = None

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return " ".join([f"{attr}:{value}" for attr,value in self.__dict__.items()])
    
    def evaluate_get_result(self):
        """To evaluate the result of a test case.
        """
        if self.evaluate_method == EcuTestCase.EcuTestCaseEvaluateMethod.EQUAL_TO:
            self.result = TestResult.PASS if self.expect_value == self.get_value else TestResult.FAIL
        elif self.evaluate_method == EcuTestCase.EcuTestCaseEvaluateMethod.NOT_EQUAL_TO:
            self.result = TestResult.PASS if self.expect_value != self.get_value else TestResult.FAIL
        elif self.evaluate_method == EcuTestCase.EcuTestCaseEvaluateMethod.IN_RANGE:
            self.result = TestResult.PASS if self.expect_value[0] < self.get_value < self.expect_value[1] else TestResult.FAIL
            
            

    

class BasicEcuDevice(metaclass=ABCMeta):
    """Basic ECU Device, which provide the API to access to the ECU global variables.

    Args:
        metaclass (_type_, optional): _description_. Defaults to ABCMeta.

    Raises:
        ValueError: _description_
        NameError: _description_

    Returns:
        _type_: _description_
    """
    @abstractmethod
    def __init__(self,logger=None):
        self.logger = logger if logger else loguru_logger
        self._wait_timeout = None
        self._w = None
        self._wFrame = None
        self._wEntryBox = None
        self._wSubmitButton = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        pass

    @abstractmethod
    def send_diag_request(self, case):
        pass

    def _compare_hex_str(self, data, exp, mask):
        mask_list = [int(mask[i * 2:(i + 1) * 2], 16) for i in range(int(len(data) / 2))]
        data_list = [int(data[i * 2:(i + 1) * 2], 16) & mask_list[i] for i in range(int(len(data) / 2))]
        exp_data_list = [int(exp[i * 2:(i + 1) * 2], 16) & mask_list[i] for i in range(int(len(data) / 2))]
        if data_list == exp_data_list:
            return TestResult.PASS
        else:
            return TestResult.FAIL


    def _timeoutfunc(self):
        self._w.destroy()
        self._wait_timeout = True


    def _get_input_with_timeout(self, label='Input dialog box', action="", timeout=5000):
        self._w = tk.Tk()
        entry_text = tk.StringVar()
        self._w.title(label)
        self._wFrame = tk.Frame(self._w, background="light yellow", padx=20, pady=20)
        self._wFrame.pack()
        self._wEntryBox = tk.Entry(self._wFrame, background="white", width=100, textvariable=entry_text)
        self._wEntryBox.focus_force()
        self._wEntryBox.pack()
        entry_text.set(action)

        def fin():
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

    def print_and_wait(self, case):
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
        self.logger.info(f"Start waiting for {text} seconds.")
        self._wait_timeout = None
        self._get_input_with_timeout("Please note on action need to be done manually.", text, timeout)
        if self._wait_timeout:
            case.result = TestResult.FAIL
        else:
            case.result = TestResult.PASS
        self.logger.info("Key received")
        self.logger.info(case)
        return TestResult.PASS


    @abstractmethod
    def set_var_value(self, case:EcuTestCase):
        """set variable value

        Args:
            case (EcuTestCase): test case object

        Returns:
            _type_: _description_
        """
        pass

    @abstractmethod
    def get_var_value(self, case:EcuTestCase):
        """get variable value

        Args:
            case (EcuTestCase): test case object
        """
        pass

    def sleep(self, case:EcuTestCase):
        """ Wait for specific seconds.

        Args:
            case (EcuTestCase): test case object

        Returns:
            _type_: _description_
        """
        time.sleep(int(case.timeout)/1000)
        case.result = TestResult.PASS
        self.logger.info(case)
        return case.result
