FROM python:3.12-slim
RUN pip install --no-cache-dir\
    pandas==3.1.0\
    numpy==2.4.5\
    scipy==1.17.0\
    matplotlib==3.11.2\
    seaborn==0.13.2\
    scikit-learn==1.9.1\
    statsmodels==0.14.5

