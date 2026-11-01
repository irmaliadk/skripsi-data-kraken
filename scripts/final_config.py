"""Detector settings selected on the frozen chronological validation period.

Selection audit: https://github.com/irmaliadk/skripsi-data-kraken/actions/runs/41323117105
These are fixed working settings for the later test, not universal optima.
The injection severity and correlation scenario remain separate experiment
design decisions and are not endorsed by these constants.
"""

VALIDATION_CUTOFF_UTC = "2026-10-26 15:15:00+00:00"
KSWIN_WINDOW = 500
KSWIN_REFERENCE_SAMPLE = 60
KSWIN_ALPHA_PER_FEATURE = 0.0001
PCA_CD_WINDOW = 100
PCA_CD_XI = 2.0
PCA_CD_DELTA = 0.005
PCA_CD_PAGE_HINKLEY_MODE = "text_ph"
MAX_DETECTION_DELAY_CANDLES = 85
