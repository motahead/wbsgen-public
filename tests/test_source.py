from __future__ import annotations
from contextlib import nullcontext
import pytest
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock
from wbsgen.source import SourceFormat, atomic_write_text, ensure_output_available, extract_html_source, format_source_json, load_source, paths_refer_to_same_file, read_generated_at, read_generator_version, with_generated_at, with_generator_version
from wbsgen.version import VERSION

class TestLoadSourceTests:

    def write_source(self, directory: str, name: str, content: str | bytes) -> Path:
        path = Path(directory) / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding='utf-8')
        return path

    def test_detects_format_from_content_regardless_of_extension(self):
        cases = (('json_in_html_file', 'source.html', '{"project": {"name": "JSON"}, "tasks": []}', SourceFormat.JSON, {'project': {'name': 'JSON'}, 'tasks': []}), ('html_in_json_file_with_reversed_script_attributes', 'source.json', '<script type="application/json" id="wbsgen-source">{"project": {"name": "HTML"}, "tasks": []}</script>', SourceFormat.HTML, {'project': {'name': 'HTML'}, 'tasks': []}), ('json_object_containing_html_marker_text', 'source.html', '{"project": {"note": "<script id=\\"wbsgen-source\\" type=\\"application/json\\">ignored</script>"}, "tasks": []}', SourceFormat.JSON, {'project': {'note': '<script id="wbsgen-source" type="application/json">ignored</script>'}, 'tasks': []}))
        with tempfile.TemporaryDirectory() as directory:
            for name, filename, content, expected_format, expected_data in cases:
                with nullcontext():
                    source = load_source(self.write_source(directory, filename, content))
                    assert source.format == expected_format
                    assert source.data == expected_data

    def test_rejects_invalid_source_contents(self):
        cases = (('missing_marker', '<html><body>missing</body></html>', 'embedded source JSON not found'), ('duplicate_marker', '<script id="wbsgen-source" type="application/json">{}</script><script type="application/json" id="wbsgen-source">{}</script>', 'embedded source JSON must appear exactly once'), ('invalid_embedded_json', '<script id="wbsgen-source" type="application/json">{invalid</script>', 'invalid embedded source JSON'), ('array_embedded_json_root', '<script id="wbsgen-source" type="application/json">[]</script>', 'embedded source JSON root must be an object'), ('array_json_root', '[]', 'embedded source JSON not found'), ('array_json_with_embedded_html_source', '[]<script id="wbsgen-source" type="application/json">{"project": {}, "tasks": []}</script>', None))
        with tempfile.TemporaryDirectory() as directory:
            for name, content, expected_message in cases:
                with nullcontext():
                    path = self.write_source(directory, f'{name}.txt', content)
                    if expected_message is None:
                        assert load_source(path).format == SourceFormat.HTML
                    else:
                        with pytest.raises(ValueError, match=expected_message):
                            load_source(path)

    def test_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_source(directory, 'invalid.txt', b'\x80')
            with pytest.raises(ValueError, match='UTF-8'):
                load_source(path)

    def test_non_object_json_uses_html_source_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_source(directory, 'source.txt', '"not an object"')
            expected = {'project': {}, 'tasks': []}
            with mock.patch('wbsgen.source.extract_html_source', return_value=expected):
                source = load_source(path)
        assert source.format == SourceFormat.HTML
        assert source.data == expected

    def test_rejects_disallowed_format(self):
        cases = (('json_when_only_html_is_allowed', '{"project": {}, "tasks": []}', frozenset({SourceFormat.HTML}), 'json', 'html'), ('html_when_only_json_is_allowed', '<script id="wbsgen-source" type="application/json">{"project": {}, "tasks": []}</script>', frozenset({SourceFormat.JSON}), 'html', 'json'))
        with tempfile.TemporaryDirectory() as directory:
            for name, content, allowed, actual_format, allowed_format in cases:
                with nullcontext():
                    path = self.write_source(directory, f'{name}.txt', content)
                    with pytest.raises(ValueError, match=f'{actual_format}.*{allowed_format}'):
                        load_source(path, allowed=allowed)

    def test_extract_html_source_accepts_any_script_attribute_order(self):
        data = extract_html_source('<script data-test="source" type="application/json" id="wbsgen-source">{"project": {}, "tasks": []}</script>')
        assert data == {'project': {}, 'tasks': []}

    def test_format_source_json_uses_indented_utf8_json(self):
        formatted = format_source_json({'project': {'name': '日本語'}, 'tasks': []})
        assert formatted == '{\n  "project": {\n    "name": "日本語"\n  },\n  "tasks": []\n}'

class TestSourceMetadataTests:

    def test_read_generator_version_returns_none_without_metadata(self):
        assert read_generator_version({'project': {}, 'tasks': []}) is None
        assert read_generator_version({'_wbsgen': {}}) is None

    def test_read_generator_version_returns_string_metadata(self):
        assert read_generator_version({'_wbsgen': {'generatorVersion': '1.2.3'}}) == '1.2.3'

    def test_read_generator_version_rejects_invalid_metadata_shape(self):
        for data, message in (({'_wbsgen': None}, '_wbsgen.*object'), ({'_wbsgen': []}, '_wbsgen.*object'), ({'_wbsgen': {'generatorVersion': None}}, 'generatorVersion.*string'), ({'_wbsgen': {'generatorVersion': 1}}, 'generatorVersion.*string')):
            with nullcontext():
                with pytest.raises(ValueError, match=message):
                    read_generator_version(data)

    def test_with_generator_version_deep_copies_and_preserves_unknown_metadata(self):
        original = {'project': {'name': 'P'}, '_wbsgen': {'generatorVersion': 'old', 'extension': {'keep': True}}}
        result = with_generator_version(original)
        assert result['_wbsgen'] == {'generatorVersion': VERSION, 'extension': {'keep': True}}
        assert original['_wbsgen'] == {'generatorVersion': 'old', 'extension': {'keep': True}}
        assert result['_wbsgen'] is not original['_wbsgen']
        assert result['_wbsgen']['extension'] is not original['_wbsgen']['extension']

    def test_with_generator_version_adds_metadata_when_missing(self):
        result = with_generator_version({'project': {}, 'tasks': []})
        assert result['_wbsgen'] == {'generatorVersion': VERSION}

    def test_with_generator_version_rejects_invalid_existing_metadata(self):
        for data, message in (({'_wbsgen': None}, '_wbsgen.*object'), ({'_wbsgen': []}, '_wbsgen.*object'), ({'_wbsgen': {'generatorVersion': None}}, 'generatorVersion.*string'), ({'_wbsgen': {'generatorVersion': 1}}, 'generatorVersion.*string')):
            with nullcontext():
                with pytest.raises(ValueError, match=message):
                    with_generator_version(data)

    def test_with_generator_version_defends_against_invalid_metadata_after_validation(self):
        data = {'_wbsgen': []}
        with mock.patch('wbsgen.source.read_generator_version'):
            with pytest.raises(ValueError, match='_wbsgen metadata must be an object'):
                with_generator_version(data)

    def test_read_generated_at_returns_none_without_metadata(self):
        assert read_generated_at({'project': {}, 'tasks': []}) is None
        assert read_generated_at({'_wbsgen': {}}) is None

    def test_read_generated_at_returns_string_metadata(self):
        assert read_generated_at({'_wbsgen': {'generatedAt': '2026-07-20 15:30'}}) == '2026-07-20 15:30'

    def test_read_generated_at_rejects_invalid_metadata_shape(self):
        for data, message in (({'_wbsgen': None}, '_wbsgen.*object'), ({'_wbsgen': []}, '_wbsgen.*object'), ({'_wbsgen': {'generatedAt': None}}, 'generatedAt.*string'), ({'_wbsgen': {'generatedAt': 1}}, 'generatedAt.*string')):
            with nullcontext():
                with pytest.raises(ValueError, match=message):
                    read_generated_at(data)

    def test_with_generated_at_deep_copies_and_preserves_unknown_metadata(self):
        original = {'project': {'name': 'P'}, '_wbsgen': {'generatedAt': '2026-01-01 00:00', 'extension': {'keep': True}}}
        result = with_generated_at(original, '2026-07-20 15:30')
        assert result['_wbsgen'] == {'generatedAt': '2026-07-20 15:30', 'extension': {'keep': True}}
        assert original['_wbsgen'] == {'generatedAt': '2026-01-01 00:00', 'extension': {'keep': True}}
        assert result['_wbsgen'] is not original['_wbsgen']
        assert result['_wbsgen']['extension'] is not original['_wbsgen']['extension']

    def test_with_generated_at_adds_metadata_when_missing(self):
        result = with_generated_at({'project': {}, 'tasks': []}, '2026-07-20 15:30')
        assert result['_wbsgen'] == {'generatedAt': '2026-07-20 15:30'}

    def test_with_generated_at_defaults_to_current_local_time(self):
        with mock.patch('wbsgen.source.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 7, 20, 15, 30, 45)
            result = with_generated_at({'project': {}, 'tasks': []})
        mock_datetime.now.assert_called_once_with()
        assert result['_wbsgen'] == {'generatedAt': '2026-07-20 15:30'}

    def test_with_generated_at_rejects_invalid_existing_metadata(self):
        for data, message in (({'_wbsgen': None}, '_wbsgen.*object'), ({'_wbsgen': []}, '_wbsgen.*object'), ({'_wbsgen': {'generatedAt': None}}, 'generatedAt.*string'), ({'_wbsgen': {'generatedAt': 1}}, 'generatedAt.*string')):
            with nullcontext():
                with pytest.raises(ValueError, match=message):
                    with_generated_at(data, '2026-07-20 15:30')

    def test_with_generated_at_defends_against_invalid_metadata_after_validation(self):
        data = {'_wbsgen': []}
        with mock.patch('wbsgen.source.read_generated_at'):
            with pytest.raises(ValueError, match='_wbsgen metadata must be an object'):
                with_generated_at(data, '2026-07-20 15:30')

class TestSourceOutputSafetyTests:

    def test_paths_refer_to_same_file_handles_missing_and_existing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / 'existing.json'
            existing.write_text('{}', encoding='utf-8')
            assert paths_refer_to_same_file(existing, existing)
            assert paths_refer_to_same_file(root / 'missing.json', root / 'missing.json')
            assert not paths_refer_to_same_file(existing, root / 'other.json')

    def test_paths_refer_to_same_file_wraps_other_os_errors(self):
        input_path = mock.Mock(spec=Path)
        output_path = Path('output.html')
        input_path.samefile.side_effect = OSError('permission denied')
        with pytest.raises(ValueError, match='failed to compare HTML output'):
            paths_refer_to_same_file(input_path, output_path)

    @pytest.mark.skipif(os.name == 'nt', reason='hard links and symlinks require POSIX semantics')
    def test_paths_refer_to_same_file_detects_hard_links_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.json'
            hard_link = root / 'hard-link.json'
            symlink = root / 'symlink.json'
            source.write_text('{}', encoding='utf-8')
            os.link(source, hard_link)
            symlink.symlink_to(source)
            assert paths_refer_to_same_file(source, hard_link)
            assert paths_refer_to_same_file(source, symlink)

    def test_ensure_output_available_rejects_existing_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output.json'
            output.write_text('old', encoding='utf-8')
            with pytest.raises(ValueError, match='already exists'):
                ensure_output_available(None, output, overwrite=False)
            ensure_output_available(None, output, overwrite=True)

    @pytest.mark.skipif(os.name == 'nt', reason='hard links and symlinks require POSIX semantics')
    def test_ensure_output_available_rejects_input_and_equivalent_output_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / 'input.json'
            linked_output = root / 'output.json'
            input_path.write_text('{}', encoding='utf-8')
            os.link(input_path, linked_output)
            with pytest.raises(ValueError, match='must differ'):
                ensure_output_available(input_path, input_path, overwrite=True)
            with pytest.raises(ValueError, match='must differ'):
                ensure_output_available(input_path, linked_output, overwrite=True)

    @pytest.mark.skipif(os.name == 'nt', reason='POSIX file modes are required')
    def test_atomic_write_text_preserves_existing_regular_file_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.html'
            path.write_text('old', encoding='utf-8')
            path.chmod(416)
            atomic_write_text(path, 'new')
            assert path.read_text(encoding='utf-8') == 'new'
            assert stat.S_IMODE(path.stat().st_mode) == 416

    def test_atomic_write_text_keeps_original_and_cleans_temporary_file_on_replace_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'project.json'
            path.write_text('before\n', encoding='utf-8')
            with mock.patch('wbsgen.source.os.replace', side_effect=OSError('disk error')):
                with pytest.raises(OSError):
                    atomic_write_text(path, 'after\n')
            assert path.read_text(encoding='utf-8') == 'before\n'
            assert list(root.glob('.project.json.*.tmp')) == []

    def test_atomic_write_text_reports_temporary_name_exhaustion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project.json'
            with mock.patch('wbsgen.source.os.open', side_effect=FileExistsError):
                with pytest.raises(FileExistsError, match='failed to create temporary'):
                    atomic_write_text(path, 'after\n')

    def test_atomic_write_text_closes_descriptor_if_opening_stream_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project.json'
            with mock.patch('wbsgen.source.os.open', return_value=123), mock.patch('wbsgen.source.os.fdopen', side_effect=OSError('stream error')), mock.patch('wbsgen.source.os.close') as close:
                with pytest.raises(OSError, match='stream error'):
                    atomic_write_text(path, 'after\n')
        close.assert_called_once_with(123)

    @pytest.mark.skipif(os.name == 'nt', reason='symlinks require POSIX semantics')
    def test_atomic_write_text_replaces_symlink_without_changing_its_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'target.html'
            output = root / 'output.html'
            target.write_text('target content', encoding='utf-8')
            output.symlink_to(target)
            atomic_write_text(output, 'new output')
            assert not output.is_symlink()
            assert output.is_file()
            assert output.read_text(encoding='utf-8') == 'new output'
            assert target.read_text(encoding='utf-8') == 'target content'
