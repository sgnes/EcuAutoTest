"""A Lauterbach Device implementation."""


from python_lauterbach import PythonLauterbach
from basic_device import EcuTestCase, TestResult, BasicEcuDevice



class LauterbachEcuDevice(BasicEcuDevice):
    """A lauterbach device which provide API to access to ECU global variables.

    Args:
        BasicEcuDevice (_type_): _description_
    """
    def __init__(self, t32_config, logger=None):
        super().__init__(logger)
        self.dbg = PythonLauterbach(t32_config["T32Path"],t32_config["ElfFile"], t32_config["SetupCmm"], 
                         cpu=t32_config["CPU"], flash_cmm=t32_config["FlashCmm"], hex_file=t32_config["HexFile"])
        self.dbg.open()

    def send_diag_request(self, case):
        pass

    def set_var_value(self, case:EcuTestCase):
        self.dbg.write_variable_value(case.name, case.set_value)
        case.result = TestResult.PASS


    def get_var_value(self, case:EcuTestCase):
        value = self.dbg.read_variable_value(case.name)
        case.get_value = value
        case.evaluate_get_result()
        return value