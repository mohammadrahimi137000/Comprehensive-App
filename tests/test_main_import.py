def test_desktop_application_modules_import_without_starting_the_app():
    import main
    assert callable(main.main)
    assert main.MainWindow is not None
    import forecast_overlay
    assert forecast_overlay.ForecastOverlay is not None
