from datamodel_code_generator import PythonVersion


def test_datamodel_code_generator_accepts_python_314_target():
    assert PythonVersion("3.14") is PythonVersion.PY_314
