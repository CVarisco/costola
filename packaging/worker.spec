from pathlib import Path
import os

root = Path(SPECPATH).parent
analysis = Analysis([str(root / 'core' / 'worker_entry.py')], pathex=[str(root)])
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name='CostolaWorker', console=True,
)
collection = COLLECT(executable, analysis.binaries, analysis.datas, name='CostolaWorker')
bundle = BUNDLE(
    collection, name='CostolaWorker.app',
    bundle_identifier=os.environ.get('COSTOLA_BUNDLE_ID', 'com.cvarisco.costola.dev') + '.worker',
    info_plist={'LSBackgroundOnly': True},
)
