import os
import sys

# Добавляем корень проекта в sys.path, чтобы тесты видели модули
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
