def test_desktop_application_modules_import_without_starting_the_app():
    import main
    assert callable(main.main)
    assert main.MainWindow is not None
