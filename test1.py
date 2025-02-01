from interface.basic_device import EcuTestCase

par = {"name" : "A", "type":"set_var_value", "description":"BBB"}
       
case = EcuTestCase(name ="A", type="set_var_value", description="BBB", set_value="1")
print(case)
case = EcuTestCase(name ="A", type="get_var_value", description="BBB", set_value="1", expect_value = [4,6], evaluate_method = "IN_RANGE", evaluate_value=5)
print(case)
case.get_value = 5
case.evaluate_get_result()
case = EcuTestCase(name ="A", type="set_var_value", description="BBB")
print(case)

print(case)
pass