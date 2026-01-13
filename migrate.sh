#!/bin/bash
set -e

echo "Migrating MyCC to MyLangCompiler..."

# 1. Rename Directories
if [ -d "MyCC" ]; then
    mv MyCC MyLangCompiler
    echo "Renamed MyCC -> MyLangCompiler"
fi

if [ -d "MyCCLinker" ]; then
    mv MyCCLinker MyLangLinker
    echo "Renamed MyCCLinker -> MyLangLinker"
fi

# 2. Rename Files
if [ -f "MyTester/cc-test.py" ]; then
    mv MyTester/cc-test.py MyTester/mlc-test.py
    echo "Renamed MyTester/cc-test.py -> MyTester/mlc-test.py"
fi

# 3. Rename Binaries (if they exist)
if [ -f "MyLangCompiler/mycc" ]; then
    mv MyLangCompiler/mycc MyLangCompiler/mlc
    echo "Renamed binary mycc -> mlc"
fi
if [ -f "MyLangLinker/mycclinker" ]; then
    mv MyLangLinker/mycclinker MyLangLinker/mllinker
    echo "Renamed binary mycclinker -> mllinker"
fi

# 4. Text Replacements
# MyCCLinker -> MyLangLinker
grep -rl "MyCCLinker" . --exclude-dir=.git --exclude=migrate.sh | xargs sed -i 's/MyCCLinker/MyLangLinker/g'

# MyCC -> MyLangCompiler
grep -rl "MyCC" . --exclude-dir=.git --exclude=migrate.sh | xargs sed -i 's/MyCC/MyLangCompiler/g'

# mycclinker -> mllinker
grep -rl "mycclinker" . --exclude-dir=.git --exclude=migrate.sh | xargs sed -i 's/mycclinker/mllinker/g'

# mycc -> mlc
grep -rl "mycc" . --exclude-dir=.git --exclude=migrate.sh | xargs sed -i 's/mycc/mlc/g'

echo "Migration complete!"
