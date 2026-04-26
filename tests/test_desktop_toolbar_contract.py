from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW_PATH = ROOT / "src/offline_gis_app/client_backend/desktop/main_window.py"
CONTROLLER_PATH = ROOT / "src/offline_gis_app/client_backend/desktop/controller.py"
ICON_REGISTRY_PATH = (
    ROOT / "src/offline_gis_app/client_backend/desktop/icon_registry.py"
)


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_node(module: ast.Module, class_name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Class not found: {class_name}")


def _class_constant(class_node: ast.ClassDef, name: str):
    for node in class_node.body:
        value = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    break
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value = node.value
        if value is not None:
            return ast.literal_eval(value)
    raise AssertionError(f"Constant not found: {name}")


def _module_constant(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Constant not found: {name}")


def _toolbar_labels_and_keys() -> tuple[list[str], list[str]]:
    module = _module_ast(MAIN_WINDOW_PATH)
    main_window = _class_node(module, "MainWindow")
    toolbar_groups = _class_constant(main_window, "TOOLBAR_GROUPS")
    labels: list[str] = []
    keys: list[str] = []
    for _group_name, entries in toolbar_groups:
        for label, key in entries:
            labels.append(label)
            keys.append(key)
    return labels, keys


def _controller_handler_labels() -> set[str]:
    module = _module_ast(CONTROLLER_PATH)
    controller = _class_node(module, "DesktopController")
    for node in controller.body:
        if (
            not isinstance(node, ast.FunctionDef)
            or node.name != "handle_toolbar_action"
        ):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign):
                continue
            if (
                not isinstance(statement.target, ast.Name)
                or statement.target.id != "handlers"
            ):
                continue
            if not isinstance(statement.value, ast.Dict):
                continue
            labels = set()
            for key in statement.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    labels.add(key.value)
            return labels
    raise AssertionError("Toolbar handlers dict not found")


def test_toolbar_icon_manifest_has_entries_for_all_toolbar_keys() -> None:
    _labels, toolbar_keys = _toolbar_labels_and_keys()
    icon_manifest = _module_constant(_module_ast(ICON_REGISTRY_PATH), "ICON_MANIFEST")

    missing = [key for key in toolbar_keys if key not in icon_manifest]
    assert not missing, f"Toolbar icon keys missing in ICON_MANIFEST: {missing}"


def test_toolbar_icon_manifest_uses_unique_icons_for_toolbar_keys() -> None:
    _labels, toolbar_keys = _toolbar_labels_and_keys()
    icon_manifest = _module_constant(_module_ast(ICON_REGISTRY_PATH), "ICON_MANIFEST")

    filenames = [icon_manifest[key] for key in toolbar_keys]
    duplicates = sorted({name for name in filenames if filenames.count(name) > 1})
    assert not duplicates, (
        f"Toolbar icon filenames should be unique per action, duplicates: {duplicates}"
    )


def test_controller_toolbar_handlers_cover_all_toolbar_labels() -> None:
    toolbar_labels, _toolbar_keys = _toolbar_labels_and_keys()
    handler_labels = _controller_handler_labels()

    missing = sorted(set(toolbar_labels) - handler_labels)
    assert not missing, f"Toolbar labels without controller handlers: {missing}"


def test_add_polygon_toolbar_action_is_toggleable() -> None:
    module = _module_ast(MAIN_WINDOW_PATH)
    main_window = _class_node(module, "MainWindow")
    toggle_actions = _class_constant(main_window, "TOGGLE_ACTIONS")

    assert "Add Polygon" in set(toggle_actions)


def test_slope_aspect_toolbar_action_is_toggleable() -> None:
    module = _module_ast(MAIN_WINDOW_PATH)
    main_window = _class_node(module, "MainWindow")
    toggle_actions = _class_constant(main_window, "TOGGLE_ACTIONS")

    assert "Slope & Aspect" in set(toggle_actions)
