from tools.cleanup import CleanupTool


tool = CleanupTool()

print("\n========== CLEANUP SAFETY REPORT ==========\n")

result = tool.preview()

if not result["success"]:
    print("Cleanup scan failed.")
    print(result["message"])
    exit()

data = result["data"]

print(f"Location        : {data['location']}")
print(f"Total files     : {data['total_files']}")
print(f"Total size      : {data['total_size_mb']} MB")

print("---------------------------------------------")

print(f"Safe candidates : {data['safe_candidates']}")
print(f"Safe size       : {data['safe_size_mb']} MB")

print("---------------------------------------------")

print(f"Protected files : {data['protected_files']}")
print(f"Protected size  : {data['protected_size_mb']} MB")

print("---------------------------------------------")

print(f"Locked files    : {data['locked_files']}")
print(f"Locked size     : {data['locked_size_mb']} MB")

print("---------------------------------------------")

print(f"Unknown files   : {data['unknown_files']}")
print(f"Unknown size    : {data['unknown_size_mb']} MB")

print("\n========== SAFE CANDIDATES ==========\n")

candidates = sorted(
    data["candidates"],
    key=lambda x: x["size_bytes"],
    reverse=True
)

for index, file in enumerate(candidates[:20], start=1):

    print(f"{index}. {file['path']}")
    print(f"   Size : {file['size_mb']} MB")
    print(f"   Age  : {file['age_days']} days")
    print(f"   Type : {file['extension'] or '[none]'}")
    print(f"   Why  : {file['reason']}")

print("\nNO FILES WERE DELETED.")