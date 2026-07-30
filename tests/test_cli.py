from contextlib import nullcontext
import csv
import pytest
import io
import importlib.util
import json
import os
import re
import runpy
import stat
import tempfile
import zipfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import wbsgen
from wbsgen.source import SourceDocument, SourceFormat, extract_html_source, load_source

class TestPackageModuleImportTests:

    def test_models_and_validation_are_importable_from_package_modules(self):
        from wbsgen.models import Project, Task, ComputedTask
        from wbsgen.validation import ValidationResult, CODE_PROJECT_REQUIRED
        assert Project.__name__ == 'Project'
        assert Task.__name__ == 'Task'
        assert ComputedTask.__name__ == 'ComputedTask'
        assert CODE_PROJECT_REQUIRED == wbsgen.CODE_PROJECT_REQUIRED
        assert ValidationResult is wbsgen.ValidationResult
        assert 'Project' in wbsgen.__all__
        assert 'CODE_PROJECT_REQUIRED' in wbsgen.__all__
        assert 'ValidationResult' in wbsgen.__all__
        assert 'dataclass' in wbsgen.__all__
        assert 'field' in wbsgen.__all__
        assert hasattr(wbsgen, 'dataclass')
        assert hasattr(wbsgen, 'field')

class TestCliModuleTests:

    def test_cli_main_is_public_entrypoint(self):
        from wbsgen.cli import main
        assert main is wbsgen.main

    def test_package_module_entrypoint_delegates_to_cli_main(self):
        import wbsgen.__main__ as module_main
        with mock.patch('wbsgen.cli.main', return_value=0) as main:
            assert module_main.main(['version']) == 0
        main.assert_called_once_with(['version'])

    def test_package_module_entrypoint_exits_with_cli_result_when_run_as_module(self):
        with mock.patch('wbsgen.cli.main', return_value=7) as main:
            with pytest.raises(SystemExit, match='7'):
                runpy.run_module('wbsgen.__main__', run_name='__main__')
        main.assert_called_once_with(None)

class TestZipappBuildTests:

    def test_atomic_xlsx_save_cleans_temporary_file_when_replace_fails(self):

        class Workbook:

            def save(self, path):
                Path(path).write_text('workbook', encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.xlsx'
            with mock.patch('wbsgen.cli.os.replace', side_effect=OSError('disk full')):
                with pytest.raises(OSError):
                    wbsgen.cli._atomic_save_workbook(Workbook(), output)
            assert not list(Path(directory).glob('.report.xlsx.*.tmp'))

    def test_runtime_dependencies_are_exactly_pinned(self):
        requirements = [line for line in Path('requirements.txt').read_text(encoding='utf-8').splitlines() if line and (not line.startswith('#'))]
        assert requirements == ['openpyxl==3.1.5', 'et_xmlfile==2.0.0']

    def test_build_zipapp_creates_archive_with_package_and_assets(self):
        spec = importlib.util.spec_from_file_location('build_zipapp', Path('tools/build_zipapp.py'))
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'wbsgen.pyz'
            built = module.build_zipapp(target)
            assert built == target.resolve()
            assert target.exists()
            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
        assert '__main__.py' in names
        assert 'wbsgen/__main__.py' in names
        assert 'wbsgen/render/assets/page.html' in names
        assert 'wbsgen/render/assets/style.css' in names
        assert 'openpyxl/__init__.py' in names
        assert 'et_xmlfile/__init__.py' in names
        assert any(('openpyxl' in name and 'LICEN' in name.upper() for name in names))

class TestV2ParserContractTests:

    def test_accepts_holiday_import_gov(self):
        args = wbsgen.parse_args(['holiday', 'import-gov', 'project.html', '--csv', 'holidays.csv'])
        assert args.holiday_command == 'import-gov'
        assert args.csv_path == Path('holidays.csv')


    def test_accepts_every_v2_command_form(self):
        cases = (('init', ('init', 'project.json')), ('template', ('template', 'template.json')), ('generate', ('generate', 'project.json', '-o', 'project.html')), ('refresh', ('refresh', 'project.html')), ('validate', ('validate', 'source')), ('version', ('version',)), ('version input', ('version', 'source')), ('export json', ('export', 'json', 'project.html')), ('export xlsx', ('export', 'xlsx', 'source', '-o', 'report.xlsx')), ('project show', ('project', 'show', 'project.html')), ('project update', ('project', 'update', 'project.html', '--name', 'P')), ('task add', ('task', 'add', 'project.html', '--id', '1', '--name', 'T')), ('task update', ('task', 'update', 'project.html', '--id', '1', '--progress', '10')), ('task show', ('task', 'show', 'project.html', '--id', '1')), ('task remove', ('task', 'remove', 'project.html', '--id', '1')), ('task move', ('task', 'move', 'project.html', '--id', '1', '--to', '2')), ('milestone add', ('milestone', 'add', 'project.html', '--date', '2026-06-01', '--name', 'M')), ('milestone update', ('milestone', 'update', 'project.html', '--name', 'M', '--new-name', 'N')), ('milestone show', ('milestone', 'show', 'project.html')), ('milestone remove', ('milestone', 'remove', 'project.html', '--name', 'M')), ('holiday add', ('holiday', 'add', 'project.html', '--date', '2026-06-01')), ('holiday update', ('holiday', 'update', 'project.html', '--date', '2026-06-01', '--new-date', '2026-06-02')), ('holiday show', ('holiday', 'show', 'project.html')), ('holiday remove', ('holiday', 'remove', 'project.html', '--date', '2026-06-01')), ('holiday merge', ('holiday', 'merge', 'project.html', '--from', 'holidays.json')), ('display show', ('display', 'show', 'project.html')), ('display update standard', ('display', 'update', 'standard', 'project.html', '--visible', 'all,-comment')), ('display update analysis', ('display', 'update', 'analysis', 'project.html', '--order', 'assignee,delta')), ('display update layers', ('display', 'update', 'layers', 'project.html', '--visible', 'all,-tooltip')))
        for label, argv in cases:
            with nullcontext():
                assert wbsgen.parse_args(argv).command == argv[0]

    def test_rejects_unsupported_current_options(self):
        invalid_argv = (('export', 'json', 'project.html', '--overwrite'), ('holiday', 'update', 'project.html', '--date', '2026-06-01', '--name', '休日', '--clear', 'name'), ('display', 'update', 'standard', 'project.html', '--visible', 'all', '--clear', 'visible'))
        for argv in invalid_argv:
            with nullcontext():
                with pytest.raises(SystemExit) as context:
                    wbsgen.parse_args(argv)
                assert context.value.code == 2

    def test_rejects_display_layers_value_and_clear_conflict(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['display', 'update', 'layers', 'project.html', '--visible', 'all', '--clear', 'visible'])
        assert context.value.code == 2

    def test_rejects_display_standard_width_value_and_clear_conflict(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['display', 'update', 'standard', 'project.html', '--width', 'name=300', '--clear', 'width'])
        assert context.value.code == 2

    def test_rejects_display_analysis_order_value_and_clear_conflict(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['display', 'update', 'analysis', 'project.html', '--order', 'delta', '--clear', 'order'])
        assert context.value.code == 2

    def test_rejects_invalid_width_argument_format(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['display', 'update', 'standard', 'project.html', '--width', 'name'])
        assert context.value.code == 2
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['display', 'update', 'standard', 'project.html', '--width', 'name=abc'])
        assert context.value.code == 2

    def test_task_show_accepts_complement_flag(self):
        args = wbsgen.parse_args(['task', 'show', 'project.html', '--id', '1', '--complement'])
        assert args.complement is True

    def test_task_show_rejects_old_include_generated_flag_name(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'show', 'project.html', '--id', '1', '--include-generated'])
        assert context.value.code == 2

    def test_task_add_help_documents_wbs_id_format_and_examples(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'add', '--help'])
        assert context.value.code == 0
        help_text = stdout.getvalue()
        assert 'Dot-separated positive integers; no leading zeros.' in help_text
        assert 'EXAMPLES:' in help_text
        assert 'wbsgen task add project.html --id 2.1' in help_text

    def test_task_add_accepts_auto_id_forms_and_rejects_id_parent_conflicts(self):
        explicit = wbsgen.parse_args(['task', 'add', 'project.html', '--id', '1', '--name', 'T'])
        child = wbsgen.parse_args(['task', 'add', 'project.html', '--parent-id', '1', '--name', 'T'])
        root = wbsgen.parse_args(['task', 'add', 'project.html', '--name', 'T'])

        assert (explicit.id, explicit.parent_id) == ('1', None)
        assert (child.id, child.parent_id) == (None, '1')
        assert (root.id, root.parent_id) == (None, None)
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'add', 'project.html', '--id', '1', '--parent-id', '1', '--name', 'T'])
        assert context.value.code == 2

    def test_task_add_help_documents_auto_id_examples_and_exclusivity(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'add', '--help'])
        assert context.value.code == 0
        help_text = stdout.getvalue()

        assert '--parent-id' in help_text
        assert 'wbsgen task add project.html --parent-id 2' in help_text
        assert 'wbsgen task add project.html --name "Release"' in help_text
        assert 'cannot be used with --id' in help_text.lower()

    def test_task_move_help_documents_destination_id_and_examples(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'move', '--help'])
        assert context.value.code == 0
        help_text = stdout.getvalue()
        assert 'Destination WBS ID' in help_text
        assert 'wbsgen task move project.html --id 2.1 --to 3.1' in help_text

    def test_task_show_help_documents_complement_examples(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['task', 'show', '--help'])
        assert context.value.code == 0
        help_text = stdout.getvalue()
        assert 'wbsgen task show project.html --id 2.1 --complement' in help_text

    def test_generate_refresh_validate_version_help_document_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['generate', '--help'],
                ['Input project JSON file.', 'Output HTML file to write.', 'EXAMPLES:', 'wbsgen generate project.json -o project.html'],
            ),
            (
                ['refresh', '--help'],
                ['HTML source-of-truth file to regenerate in place.', 'EXAMPLES:', 'wbsgen refresh project.html'],
            ),
            (
                ['validate', '--help'],
                ['JSON or WBS-GEN HTML file to validate.', 'EXAMPLES:', 'wbsgen validate project.html'],
            ),
            (
                ['version', '--help'],
                ['Omit to print the CLI version only.', 'EXAMPLES:', 'wbsgen version\n', 'wbsgen version project.html'],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_task_remaining_arguments_document_input_html_clear_direct_recursive(self):
        for argv, expected_snippets in (
            (
                ['task', 'show', '--help'],
                ['HTML source-of-truth file to read or update.', 'Limit parents/children to the direct parent'],
            ),
            (
                ['task', 'update', '--help'],
                ['Clear one or more optional task fields', '--clear assignee comment'],
            ),
            (
                ['task', 'remove', '--help'],
                ['Also remove all descendant tasks.', 'Required when the task has children.'],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_export_help_documents_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['export', 'json', '--help'],
                ['Omit to print to stdout.', 'Requires -o/--output.', 'EXAMPLES:', 'wbsgen export json project.html -o project.json'],
            ),
            (
                ['export', 'xlsx', '--help'],
                ['Higher values shrink mark text', 'default: 1', 'EXAMPLES:', 'wbsgen export xlsx project.html -o report.xlsx'],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_project_help_documents_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['project', 'show', '--help'],
                ['HTML source-of-truth file to read.', 'EXAMPLES:', 'wbsgen project show project.html'],
            ),
            (
                ['project', 'update', '--help'],
                [
                    'Clear one or more optional project fields',
                    '--clear end-date issue-base-url',
                    'EXAMPLES:',
                    'wbsgen project update project.html --status-date 2026-08-01',
                ],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_milestone_help_documents_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['milestone', 'add', '--help'],
                ['Milestone date (YYYY-MM-DD).', 'Milestone name.', 'EXAMPLES:', 'wbsgen milestone add project.html --date 2026-08-10 --name "Release review"'],
            ),
            (
                ['milestone', 'update', '--help'],
                ['Existing milestone name to update.', 'At least one of --new-date or --new-name is required.', 'EXAMPLES:'],
            ),
            (
                ['milestone', 'show', '--help'],
                ['HTML source-of-truth file to read.', 'EXAMPLES:', 'wbsgen milestone show project.html'],
            ),
            (
                ['milestone', 'remove', '--help'],
                ['Milestone name to remove.', 'disambiguate when multiple milestones share the same name', 'EXAMPLES:'],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_holiday_help_documents_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['holiday', 'add', '--help'],
                ['Holiday date (YYYY-MM-DD).', 'EXAMPLES:', 'wbsgen holiday add project.html --date 2026-08-11 --name "Mountain Day"'],
            ),
            (
                ['holiday', 'update', '--help'],
                ['Existing holiday date (YYYY-MM-DD) to update.', 'At least one of --name, --clear, or --new-date is required.', 'EXAMPLES:'],
            ),
            (
                ['holiday', 'show', '--help'],
                ['HTML source-of-truth file to read.', 'EXAMPLES:'],
            ),
            (
                ['holiday', 'remove', '--help'],
                ['Holiday date (YYYY-MM-DD) to remove.', 'EXAMPLES:'],
            ),
            (
                ['holiday', 'merge', '--help'],
                ['External JSON file with a top-level holidays array', 'EXAMPLES:', 'wbsgen holiday merge project.html --from holidays.json'],
            ),
            (
                ['holiday', 'import-gov', '--help'],
                ['Uses no network access.', 'EXAMPLES:', 'wbsgen holiday import-gov project.html --csv holidays.csv'],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_display_help_documents_arguments_and_examples(self):
        for argv, expected_snippets in (
            (
                ['display', 'show', '--help'],
                ['HTML source-of-truth file to read.', 'EXAMPLES:', 'wbsgen display show project.html'],
            ),
            (
                ['display', 'update', 'standard', '--help'],
                [
                    'keys: planned, actual, progress, expected, issue, comment, assignee',
                    "must be combined with '*'/'all'",
                    'keys: name, assignee, comment',
                    'value >= 40',
                    'keys: assignee, planned-period, actual-period, progress, expected-progress, issue',
                    'Repeat the flag to clear several',
                    'EXAMPLES:',
                    'wbsgen display update standard project.html --visible all,-comment',
                ],
            ),
            (
                ['display', 'update', 'analysis', '--help'],
                [
                    'keys: assignee, progress, expected-progress, delta, delay, pace',
                    'EXAMPLES:',
                    'wbsgen display update analysis project.html --order assignee,delta',
                ],
            ),
            (
                ['display', 'update', 'layers', '--help'],
                [
                    'keys: inazuma, actual, highlight, tooltip, delayHighlight, milestone',
                    "must be combined with '*'/'all'",
                    'EXAMPLES:',
                    'wbsgen display update layers project.html --visible all,-tooltip',
                ],
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
                wbsgen.parse_args(argv)
            assert context.value.code == 0
            help_text = stdout.getvalue()
            for snippet in expected_snippets:
                assert snippet in help_text, f"{argv}: missing {snippet!r}"

    def test_version_option_exits_before_a_subcommand_is_required(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), pytest.raises(SystemExit) as context:
            wbsgen.parse_args(('--version',))
        assert context.value.code == 0
        assert stdout.getvalue() == 'wbsgen development\n'

class TestV2LifecycleCommandTests:

    def _source_json(self, directory: str) -> Path:
        path = Path(directory) / 'project.json'
        path.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
        return path

    def test_generate_refresh_validate_version_and_export_json(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            html = Path(directory) / 'project.html'
            exported = Path(directory) / 'exported.json'
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            source_before = source.read_bytes()
            assert wbsgen.main(['refresh', str(html)]) == 0
            assert source.read_bytes() == source_before
            assert wbsgen.main(['export', 'json', str(html), '-o', str(exported)]) == 0
            version_stdout = io.StringIO()
            with redirect_stdout(version_stdout):
                assert wbsgen.main(['version', str(html)]) == 0
            assert json.loads(version_stdout.getvalue()) == {'cliVersion': 'development', 'generatorVersion': 'development'}
            validation_stdout = io.StringIO()
            with redirect_stdout(validation_stdout):
                assert wbsgen.main(['validate', str(html), '--json']) == 0
            assert json.loads(validation_stdout.getvalue())['ok']

    def test_generate_and_refresh_stamp_generated_at_with_current_local_time(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            html = Path(directory) / 'project.html'
            with mock.patch('wbsgen.source.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 7, 20, 15, 30, 0)
                assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert load_source(html).data['_wbsgen']['generatedAt'] == '2026-07-20 15:30'
            with mock.patch('wbsgen.source.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 7, 21, 9, 5, 0)
                assert wbsgen.main(['refresh', str(html)]) == 0
            assert load_source(html).data['_wbsgen']['generatedAt'] == '2026-07-21 09:05'

    def test_init_and_template_do_not_stamp_generated_at(self):
        with tempfile.TemporaryDirectory() as directory:
            init_path = Path(directory) / 'init.json'
            template_path = Path(directory) / 'template.json'
            assert wbsgen.main(['init', str(init_path)]) == 0
            assert wbsgen.main(['template', str(template_path)]) == 0
            assert 'generatedAt' not in json.loads(init_path.read_text(encoding='utf-8'))['_wbsgen']
            assert 'generatedAt' not in json.loads(template_path.read_text(encoding='utf-8'))['_wbsgen']

    def test_generate_merges_supplemental_holidays_without_mutating_json_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            holidays = Path(directory) / 'holidays.json'
            holidays.write_text(json.dumps({'holidays': [{'date': '2026-07-20', 'name': '海の日'}]}), encoding='utf-8')
            html = Path(directory) / 'project.html'
            assert wbsgen.main(['generate', str(source), '-o', str(html), '--holidays', str(holidays)]) == 0
            assert 'holidays' not in json.loads(source.read_text(encoding='utf-8'))
            exported = load_source(html)
            assert exported.data['holidays'] == [{'date': '2026-07-20', 'name': '海の日'}]

    def test_generated_outputs_require_overwrite_and_never_accept_same_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            html = Path(directory) / 'project.html'
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 1
            assert wbsgen.main(['generate', str(source), '-o', str(html), '--overwrite']) == 0
            assert wbsgen.main(['generate', str(source), '-o', str(source), '--overwrite']) == 1

    def test_html_source_of_truth_end_to_end_including_xlsx_and_legacy_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            html = Path(directory) / 'project.html'
            xlsx = Path(directory) / 'project.xlsx'
            exported = Path(directory) / 'exported.json'
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            data = load_source(html).data
            data.pop('_wbsgen')
            html.write_text(wbsgen.render_html(data, wbsgen.build_project_model(data)), encoding='utf-8')
            assert wbsgen.main(['project', 'update', str(html), '--name', '更新後']) == 0
            assert wbsgen.main(['refresh', str(html)]) == 0
            assert wbsgen.main(['validate', str(html)]) == 0
            assert wbsgen.main(['export', 'xlsx', str(html), '-o', str(xlsx)]) == 0
            assert wbsgen.main(['export', 'json', str(html), '-o', str(exported)]) == 0
            assert xlsx.exists()
            exported_metadata = json.loads(exported.read_text(encoding='utf-8'))['_wbsgen']
            assert exported_metadata['generatorVersion'] == 'development'
            assert re.search('^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$', exported_metadata['generatedAt'])

    def test_version_without_input_and_export_json_to_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_json(directory)
            html = Path(directory) / 'project.html'
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                assert wbsgen.main(['version']) == 0
            assert stdout.getvalue() == 'development\n'
            with redirect_stdout((stdout := io.StringIO())):
                assert wbsgen.main(['export', 'json', str(html)]) == 0
            assert json.loads(stdout.getvalue())['project'] == {'name': 'P'}

    def test_generate_and_xlsx_reject_invalid_source_without_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid, html, xlsx = (root / 'invalid.json', root / 'out.html', root / 'out.xlsx')
            invalid.write_text(json.dumps({'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(invalid), '-o', str(html)]) == 1
            assert not html.exists()
            assert wbsgen.main(['export', 'xlsx', str(invalid), '-o', str(xlsx)]) == 1
            assert not xlsx.exists()

    def test_refresh_rejects_invalid_embedded_source(self):
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / 'invalid.html'
            html.write_text('<script id="wbsgen-source" type="application/json">{"tasks": []}</script>', encoding='utf-8')
            assert wbsgen.main(['refresh', str(html)]) == 1

class TestV2HtmlMutationCommandTests:

    def test_all_html_mutation_and_show_command_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, html = (root / 'project.json', root / 'project.html')
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            commands = (['project', 'show', str(html)], ['project', 'update', str(html), '--name', 'P2'], ['task', 'add', str(html), '--id', '1', '--name', 'T'], ['task', 'show', str(html), '--id', '1'], ['task', 'update', str(html), '--id', '1', '--progress', '10'], ['milestone', 'add', str(html), '--date', '2026-06-01', '--name', 'M'], ['milestone', 'show', str(html)], ['milestone', 'update', str(html), '--name', 'M', '--new-name', 'M2'], ['milestone', 'remove', str(html), '--name', 'M2'], ['holiday', 'add', str(html), '--date', '2026-06-02'], ['holiday', 'show', str(html)], ['holiday', 'update', str(html), '--date', '2026-06-02', '--name', 'H'], ['holiday', 'remove', str(html), '--date', '2026-06-02'], ['display', 'show', str(html)], ['task', 'remove', str(html), '--id', '1'])
            for command in commands:
                with nullcontext():
                    assert wbsgen.main(command) == 0

    def test_invalid_html_candidates_and_missing_inputs_do_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, html = (root / 'project.json', root / 'project.html')
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            before = html.read_bytes()
            assert wbsgen.main(['task', 'add', str(html), '--id', '1', '--name', 'T']) == 0
            before = html.read_bytes()
            assert wbsgen.main(['task', 'update', str(html), '--id', '1', '--progress', '101']) == 1
            assert html.read_bytes() == before
            assert wbsgen.main(['refresh', str(root / 'missing.html')]) == 1

    def test_display_update_rejects_invalid_values_via_validation_pipeline_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, html = (root / 'project.json', root / 'project.html')
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            before = html.read_bytes()
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['display', 'update', 'standard', str(html), '--width', 'name=30'])
            assert exit_code == 1
            assert 'DISPLAY_INVALID' in stderr.getvalue()
            assert html.read_bytes() == before
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['display', 'update', 'analysis', str(html), '--order', 'unknown-key'])
            assert exit_code == 1
            assert 'DISPLAY_INVALID' in stderr.getvalue()
            assert html.read_bytes() == before

    def test_mutations_update_html_and_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.json'
            html = root / 'project.html'
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert wbsgen.main(['task', 'add', str(html), '--id', '1', '--name', 'Task']) == 0
            assert wbsgen.main(['display', 'update', 'standard', str(html), '--visible', 'all,-comment']) == 0
            before = html.read_bytes()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                assert wbsgen.main(['task', 'move', str(html), '--id', '1', '--to', '2', '--dry-run']) == 0
            assert html.read_bytes() == before
            assert '"id": "2"' in stdout.getvalue()
            assert wbsgen.main(['task', 'move', str(html), '--id', '1', '--to', '2']) == 0
            payload = load_source(html).data
            assert payload['tasks'][0]['id'] == '2'
            assert payload['display'] == {'standard': {'columns': {'visible': ['*', '-comment']}}}

    def test_project_update_stamps_generated_at_and_dry_run_does_not_write_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.json'
            html = root / 'project.html'
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            with mock.patch('wbsgen.source.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 7, 20, 15, 30, 0)
                assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert load_source(html).data['_wbsgen']['generatedAt'] == '2026-07-20 15:30'
            before = html.read_bytes()
            stdout = io.StringIO()
            with mock.patch('wbsgen.source.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 7, 21, 9, 0, 0)
                with redirect_stdout(stdout):
                    assert wbsgen.main(['project', 'update', str(html), '--name', '更新後', '--dry-run']) == 0
            assert html.read_bytes() == before
            assert '"generatedAt": "2026-07-21 09:00"' in stdout.getvalue()
            assert load_source(html).data['_wbsgen']['generatedAt'] == '2026-07-20 15:30'
            with mock.patch('wbsgen.source.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 7, 21, 9, 0, 0)
                assert wbsgen.main(['project', 'update', str(html), '--name', '更新後']) == 0
            assert load_source(html).data['_wbsgen']['generatedAt'] == '2026-07-21 09:00'

    def test_show_commands_are_read_only_and_holiday_merge_uses_common_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.json'
            html = root / 'project.html'
            holidays = root / 'holidays.json'
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            holidays.write_text(json.dumps({'holidays': [{'date': '2026-07-20', 'name': '海の日'}]}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert wbsgen.main(['holiday', 'merge', str(html), '--from', str(holidays)]) == 0
            before = html.read_bytes()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                assert wbsgen.main(['holiday', 'show', str(html)]) == 0
            assert html.read_bytes() == before
            assert json.loads(stdout.getvalue()) == [{'date': '2026-07-20', 'name': '海の日'}]

    def test_task_add_and_update_write_and_clear_assignee_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, html = (root / 'project.json', root / 'project.html')
            source.write_text(json.dumps({'project': {'name': 'P'}, 'tasks': []}), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0
            assert wbsgen.main(['task', 'add', str(html), '--id', '1', '--name', 'T', '--assignee', '担当者A']) == 0
            payload = load_source(html).data
            assert payload['tasks'][0]['assignee'] == '担当者A'
            assert wbsgen.main(['task', 'update', str(html), '--id', '1', '--assignee', '担当者B']) == 0
            assert load_source(html).data['tasks'][0]['assignee'] == '担当者B'
            assert wbsgen.main(['task', 'update', str(html), '--id', '1', '--clear', 'assignee']) == 0
            assert 'assignee' not in load_source(html).data['tasks'][0]

    def test_task_add_auto_assigns_child_and_top_level_ids_without_writing_on_error_or_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.json'
            html = root / 'project.html'
            source.write_text(json.dumps({
                'project': {'name': 'P'},
                'tasks': [
                    {'id': '1', 'name': '親'},
                    {'id': '1.1', 'name': '子1'},
                    {'id': '1.2', 'name': '子2'},
                    {'id': '3', 'name': '既存トップレベル'},
                ],
            }), encoding='utf-8')
            assert wbsgen.main(['generate', str(source), '-o', str(html)]) == 0

            assert wbsgen.main(['task', 'add', str(html), '--parent-id', '1', '--name', '子3']) == 0
            assert [task['id'] for task in load_source(html).data['tasks']] == ['1', '1.1', '1.2', '3', '1.3']
            assert wbsgen.main(['task', 'add', str(html), '--name', '新規トップレベル']) == 0
            assert load_source(html).data['tasks'][-1]['id'] == '4'

            before = html.read_bytes()
            assert wbsgen.main(['task', 'add', str(html), '--parent-id', '9', '--name', '失敗']) == 1
            assert html.read_bytes() == before
            assert wbsgen.main(['task', 'add', str(html), '--name', '下書き', '--dry-run']) == 0
            assert html.read_bytes() == before


class TestInitCommandTests:

    def test_main_init_writes_default_project_template_as_utf8_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'project.json'
            exit_code = wbsgen.main(['init', str(output_path)])
            assert exit_code == 0
            assert json.loads(output_path.read_text(encoding='utf-8')) == {'project': {'name': '新しいプロジェクト'}, 'tasks': [], '_wbsgen': {'generatorVersion': 'development'}}

    def test_main_init_uses_name_for_project_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'project.json'
            exit_code = wbsgen.main(['init', str(output_path), '--name', 'Webサイト刷新'])
            assert exit_code == 0
            assert json.loads(output_path.read_text(encoding='utf-8'))['project']['name'] == 'Webサイト刷新'

    def test_main_init_rejects_existing_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'project.json'
            output_path.write_text('{}', encoding='utf-8')
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['init', str(output_path)])
            assert exit_code == 1
            assert 'already exists' in stderr.getvalue()

    def test_main_init_rejects_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'missing' / 'project.json'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['init', str(output_path)])
            assert exit_code == 1
            assert 'parent directory does not exist' in stderr.getvalue()

    def test_main_init_rejects_parent_path_that_is_a_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent_path = Path(tmp) / 'not-a-directory'
            parent_path.write_text('not a directory', encoding='utf-8')
            output_path = parent_path / 'project.json'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['init', str(output_path)])
            assert exit_code == 1
            assert 'parent directory does not exist' in stderr.getvalue()

    def test_main_init_rejects_blank_project_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'project.json'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['init', str(output_path), '--name', '   '])
            assert exit_code == 1
            assert 'project name must not be blank' in stderr.getvalue()

    def test_parse_args_rejects_json_for_init(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['init', 'output.json', '--json'])
        assert context.value.code == 2

class TestTemplateCommandTests:
    EXPECTED_TEMPLATE = {'project': {'name': '新しいプロジェクト', 'startDate': 'YYYY-MM-DD', 'endDate': 'YYYY-MM-DD', 'statusDate': 'YYYY-MM-DD', 'issueBaseUrl': 'https://github.com/your_account/your_repo/issues/'}, 'display': {'standard': {'columns': {'visible': ['*'], 'width': {'name': 220, 'assignee': 56, 'comment': 220}}}, 'analysis': {'columns': {}}, 'layers': {'visible': ['*']}}, 'holidays': [{'date': 'YYYY-MM-DD', 'name': '休日名'}], 'milestones': [{'date': 'YYYY-MM-DD', 'name': 'マイルストーン名'}], 'tasks': [{'id': '1', 'name': 'タスク名', 'assignee': '担当者名', 'plannedStart': 'YYYY-MM-DD', 'plannedDuration': 1, 'actualStart': 'YYYY-MM-DD', 'actualEnd': None, 'progress': 0, 'issue': 1, 'comment': 'タスクの補足'}], '_wbsgen': {'generatorVersion': 'development'}}

    def test_main_template_writes_full_editing_skeleton_as_utf8_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'template.json'
            exit_code = wbsgen.main(['template', str(output_path)])
            output_text = output_path.read_text(encoding='utf-8')
            assert exit_code == 0
            assert json.loads(output_text) == self.EXPECTED_TEMPLATE
            assert output_text == json.dumps(self.EXPECTED_TEMPLATE, ensure_ascii=False, indent=2) + '\n'

    def test_main_template_rejects_existing_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'template.json'
            output_path.write_text('{}', encoding='utf-8')
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['template', str(output_path)])
            assert exit_code == 1
            assert 'already exists' in stderr.getvalue()

    def test_main_template_rejects_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / 'missing' / 'template.json'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['template', str(output_path)])
            assert exit_code == 1
            assert 'parent directory does not exist' in stderr.getvalue()

    def test_main_template_rejects_parent_path_that_is_a_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent_path = Path(tmp) / 'not-a-directory'
            parent_path.write_text('not a directory', encoding='utf-8')
            output_path = parent_path / 'template.json'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = wbsgen.main(['template', str(output_path)])
            assert exit_code == 1
            assert 'parent directory does not exist' in stderr.getvalue()

    def test_parse_args_rejects_name_for_template(self):
        with pytest.raises(SystemExit) as context:
            wbsgen.parse_args(['template', 'output.json', '--name', 'Webサイト刷新'])
        assert context.value.code == 2


class TestTabularExportCommands:

    def test_markdown_and_csv_export_accept_json_html_and_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "project.json"
            html = Path(directory) / "project.html"
            source.write_text(json.dumps({"project": {"name": "P", "startDate": "2026-07-01", "endDate": "2026-07-31", "statusDate": "2026-07-10"}, "tasks": []}), encoding="utf-8")
            assert wbsgen.main(["generate", str(source), "-o", str(html)]) == 0
            markdown = io.StringIO()
            with redirect_stdout(markdown):
                assert wbsgen.main(["export", "md", str(html)]) == 0
            assert "| ID | タスク名 |" in markdown.getvalue()
            output = Path(directory) / "report.csv"
            assert wbsgen.main(["export", "csv", str(source), "-o", str(output), "--encoding", "utf-8-sig"]) == 0
            assert output.read_bytes().startswith(b"\xef\xbb\xbf")
            assert next(csv.reader(output.read_text(encoding="utf-8-sig").splitlines()))[0] == "ID"

    def test_csv_accepts_sjis_alias_and_markdown_rejects_encoding(self):
        args = wbsgen.parse_args(["export", "csv", "project.json", "--encoding", "sjis"])
        assert args.encoding == "sjis"
        with pytest.raises(SystemExit):
            wbsgen.parse_args(["export", "markdown", "project.json", "--encoding", "utf-8"])
