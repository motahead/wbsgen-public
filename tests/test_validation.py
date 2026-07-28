import io
import importlib.util
import json
import tempfile
import zipfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import wbsgen

class TestValidationResultTests:

    def test_validation_result_collects_errors_and_warnings(self):
        result = wbsgen.ValidationResult()
        result.error(wbsgen.CODE_PROJECT_REQUIRED, 'project', 'project は必須です')
        result.warning(wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id', '親タスク 1 を補完しました')
        assert result.has_errors
        assert result.errors[0].level == wbsgen.LEVEL_ERROR
        assert result.errors[0].code == wbsgen.CODE_PROJECT_REQUIRED
        assert result.errors[0].path == 'project'
        assert result.warnings[0].level == wbsgen.LEVEL_WARNING
        assert result.warnings[0].code == wbsgen.CODE_MISSING_PARENT_TASK
        assert result.warnings[0].path == 'tasks[0].id'

    def test_validation_report_to_dict_returns_empty_report(self):
        report = wbsgen.validation_report_to_dict(wbsgen.ValidationResult())
        assert report == {'ok': True, 'errorCount': 0, 'warningCount': 0, 'errors': [], 'warnings': []}

    def test_validation_report_to_dict_separates_errors_and_warnings(self):
        result = wbsgen.ValidationResult()
        result.error(wbsgen.CODE_PROJECT_REQUIRED, 'project', 'project は必須です')
        result.warning(wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id', '親タスク 1 を補完しました')
        report = wbsgen.validation_report_to_dict(result)
        assert not report['ok']
        assert report['errorCount'] == 1
        assert report['warningCount'] == 1
        assert report['errors'] == [{'level': 'error', 'code': 'PROJECT_REQUIRED', 'path': 'project', 'message': 'project は必須です'}]
        assert report['warnings'] == [{'level': 'warning', 'code': 'MISSING_PARENT_TASK', 'path': 'tasks[0].id', 'message': '親タスク 1 を補完しました'}]

class TestHolidayValidationCodeTests:

    def test_holiday_validation_codes_are_defined(self):
        assert wbsgen.CODE_HOLIDAYS_INVALID == 'HOLIDAYS_INVALID'
        assert wbsgen.CODE_HOLIDAY_REQUIRED == 'HOLIDAY_REQUIRED'
        assert wbsgen.CODE_HOLIDAY_DATE_INVALID == 'HOLIDAY_DATE_INVALID'
        assert wbsgen.CODE_HOLIDAY_NAME_INVALID == 'HOLIDAY_NAME_INVALID'
        assert wbsgen.CODE_HOLIDAY_DATE_DUPLICATED == 'HOLIDAY_DATE_DUPLICATED'

    def test_holiday_validation_codes_are_distinct_from_task_date_codes(self):
        assert wbsgen.CODE_HOLIDAY_DATE_INVALID != wbsgen.CODE_TASK_DATE_INVALID
        assert wbsgen.CODE_HOLIDAY_DATE_INVALID != wbsgen.CODE_PROJECT_DATE_INVALID

class TestDisplayValidationCodeTests:

    def test_display_validation_code_is_defined(self):
        assert wbsgen.CODE_DISPLAY_INVALID == 'DISPLAY_INVALID'
