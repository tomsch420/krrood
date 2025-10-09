from __future__ import annotations

import krrood as lubm_pd_module


def _eval_if_str(ann):
    if isinstance(ann, str):
        try:
            return eval(ann, vars(lubm_pd_module))
        except Exception:
            return ann
    return ann
