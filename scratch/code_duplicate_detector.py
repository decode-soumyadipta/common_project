import ast
import os
from collections import defaultdict
from pathlib import Path

def analyze_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    try:
        tree = ast.parse(code, filename=str(file_path))
    except SyntaxError as e:
        return {
            "error": f"Syntax Error: {e}"
        }

    results = {
        "duplicate_globals": [],
        "duplicate_functions": [],
        "duplicate_methods": [],
        "duplicate_signatures": [],
    }

    # Trackers for this module
    global_names = set()
    global_duplicates = set()
    
    module_functions = set()
    module_func_duplicates = set()

    for node in tree.body:
        # 1. Global Variable Duplicates
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if name in global_names:
                        global_duplicates.add(name)
                    else:
                        global_names.add(name)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                name = node.target.id
                if name in global_names:
                    global_duplicates.add(name)
                else:
                    global_names.add(name)

        # 2. Duplicate Module-Level Function / Class Names
        elif isinstance(node, ast.FunctionDef):
            name = node.name
            if name in module_functions:
                module_func_duplicates.add(name)
            else:
                module_functions.add(name)
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if name in module_functions:
                module_func_duplicates.add(name)
            else:
                module_functions.add(name)

    for name in global_duplicates:
        results["duplicate_globals"].append(name)

    for name in module_func_duplicates:
        results["duplicate_functions"].append(name)

    # Walk classes for duplicate methods and duplicate signature parameters
    for node in ast.walk(tree):
        # 3. Duplicate Class Methods
        if isinstance(node, ast.ClassDef):
            class_methods = set()
            class_method_duplicates = set()
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    name = child.name
                    if name in class_methods:
                        class_method_duplicates.add(name)
                    else:
                        class_methods.add(name)
            for name in class_method_duplicates:
                results["duplicate_methods"].append(f"Class {node.name} -> Method {name}")

        # 4. Duplicate Signature Arguments
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arg_names = set()
            arg_duplicates = set()
            for arg in node.args.args:
                name = arg.arg
                if name in arg_names:
                    arg_duplicates.add(name)
                else:
                    arg_names.add(name)
            for arg in node.args.kwonlyargs:
                name = arg.arg
                if name in arg_names:
                    arg_duplicates.add(name)
                else:
                    arg_names.add(name)
            
            for name in arg_duplicates:
                results["duplicate_signatures"].append(f"Function {node.name} -> Argument {name}")

    return results

def main():
    root_dir = Path("src_new").resolve()
    print(f"=== Starting AST Duplicate Code Scan on: {root_dir} ===")

    total_scanned = 0
    issues_found = 0

    duplicate_globals_report = defaultdict(list)
    duplicate_functions_report = defaultdict(list)
    duplicate_methods_report = defaultdict(list)
    duplicate_signatures_report = defaultdict(list)

    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                total_scanned += 1
                res = analyze_file(file_path)
                
                if "error" in res:
                    print(f"[ERR] {file_path.relative_to(root_dir.parent)}: {res['error']}")
                    continue

                rel_path = str(file_path.relative_to(root_dir.parent))
                if res["duplicate_globals"]:
                    duplicate_globals_report[rel_path].extend(res["duplicate_globals"])
                    issues_found += len(res["duplicate_globals"])
                if res["duplicate_functions"]:
                    duplicate_functions_report[rel_path].extend(res["duplicate_functions"])
                    issues_found += len(res["duplicate_functions"])
                if res["duplicate_methods"]:
                    duplicate_methods_report[rel_path].extend(res["duplicate_methods"])
                    issues_found += len(res["duplicate_methods"])
                if res["duplicate_signatures"]:
                    duplicate_signatures_report[rel_path].extend(res["duplicate_signatures"])
                    issues_found += len(res["duplicate_signatures"])

    print(f"\nScan complete. Scanned {total_scanned} python files. Found {issues_found} potential duplication issues.")

    if issues_found == 0:
        print("\n🏆 PERFECT CODE QUALITY! Zero duplicate variables, functions, methods, or signature arguments found!")
        return

    if duplicate_globals_report:
        print("\n--- Duplicate Global Variables ---")
        for path, names in duplicate_globals_report.items():
            print(f"📄 {path}: {', '.join(names)}")

    if duplicate_functions_report:
        print("\n--- Duplicate Functions/Classes inside Module ---")
        for path, names in duplicate_functions_report.items():
            print(f"📄 {path}: {', '.join(names)}")

    if duplicate_methods_report:
        print("\n--- Duplicate Methods inside Classes ---")
        for path, names in duplicate_methods_report.items():
            print(f"📄 {path}: {', '.join(names)}")

    if duplicate_signatures_report:
        print("\n--- Duplicate Argument Names in Signatures ---")
        for path, names in duplicate_signatures_report.items():
            print(f"📄 {path}: {', '.join(names)}")

if __name__ == "__main__":
    main()
