from website import create_app

app_flask = create_app()

if __name__ == '__main__':
    app_flask.run(debug=True, host='0.0.0.0', port=5000)