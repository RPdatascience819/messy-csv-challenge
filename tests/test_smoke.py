from __future__ import annotations

import messy_csv


def test_pacote_importa_e_declara_versao() -> None:
    assert messy_csv.__version__ == "0.1.0"
