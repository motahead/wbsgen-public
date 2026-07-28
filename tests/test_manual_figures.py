import pytest
import json
from pathlib import Path
from unittest import mock

class TestManualFigureArgumentTests:

    def test_check_mode_is_selected(self):
        from tools.render_manual_figures import parse_args
        assert parse_args(['--check']).check
        assert not parse_args(['--check']).write

    def test_write_mode_is_selected(self):
        from tools.render_manual_figures import parse_args
        assert parse_args(['--write']).write
        assert not parse_args(['--write']).check

    def test_mode_is_required(self):
        from tools.render_manual_figures import parse_args
        with pytest.raises(SystemExit):
            parse_args([])

    def test_modes_are_exclusive(self):
        from tools.render_manual_figures import parse_args
        with pytest.raises(SystemExit):
            parse_args(['--check', '--write'])

class ManualFigureSourceTests:

    def test_mermaid_command_uses_mise_managed_cli(self):
        from tools.render_manual_figures import mermaid_command
        assert mermaid_command(Path('in.mmd'), Path('out.svg')) == ['mise', 'exec', 'npm:@mermaid-js/mermaid-cli@11.12.0', '--', 'mmdc', '-i', 'in.mmd', '-o', 'out.svg']

    def test_output_paths_are_kept_with_their_sources(self):
        from tools.render_manual_figures import figure_paths
        paths = figure_paths()
        assert paths['fig1_svg'] == Path('docs/manual-figures/fig1.svg')
        assert paths['fig2_html'] == Path('docs/manual-figures/fig2.html')
        assert paths['fig2_png'] == Path('docs/manual-figures/fig2.png')

class TestManualFigureInputTests:

    def load(self, name: str) -> dict:
        return json.loads(Path('examples', name).read_text(encoding='utf-8'))

    def test_fig2_is_a_clean_project_overview(self):
        data = self.load('manual-figures-fig2.json')
        assert len(data['tasks']) >= 8
        assert any(('.' in task['id'] for task in data['tasks']))
        assert any((task.get('progress') == 100 for task in data['tasks']))
        assert any((0 < task.get('progress', 0) < 100 for task in data['tasks']))
        assert len(data['holidays']) == 1
        assert len(data['milestones']) == 1

class TestManualFigureCheckTests:

    def test_check_rejects_missing_generated_output(self):
        from tools.render_manual_figures import parse_args, run
        with mock.patch('tools.render_manual_figures.figure_paths') as figure_paths:
            figure_paths.return_value = {'fig1_mmd': Path('missing.mmd'), 'fig1_svg': Path('missing.svg'), 'fig2_json': Path('missing-fig2.json'), 'fig2_html': Path('missing-fig2.html'), 'fig2_png': Path('missing-fig2.png')}
            assert run(parse_args(['--check'])) == 1
