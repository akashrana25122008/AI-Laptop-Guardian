from tools.file_inspector.inspector import FileInspector


inspector = FileInspector()

file_path = r"C:\Users\ajeet\AppData\Local\Temp\wctBEC6.tmp"

result = inspector.inspect(file_path)

print()
print("=" * 60)
print("FILE INSPECTOR TEST")
print("=" * 60)

print(result)