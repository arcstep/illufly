from illufly.api.start import main

if __name__ == "__main__":
    """
    启动illufly api服务

    使用方法：
    poetry run python -m illufly

    或者：
    poetry run python -m illufly \
    --db-path /path/to/db \
    --title "My API" \
    --description "My API Description" \
    --version "1.0.0" \
    --prefix "/v1" \
    --host "localhost" \
    --port 8080 \
    --reload

    查看帮助：
    poetry run python -m illufly --help

    """
    main() 