# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.23.3",
#     "plotly>=6.7.0",
#     "requests>=2.34.2",
# ]
# ///

import marimo

__generated_with = "0.23.13"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import urllib.request as req
    import plotly.io as pio
    import requests

    mo.Html(
        f"<style>{req.urlopen('https://raw.githubusercontent.com/janithcyapa/Engineering-Codex/refs/heads/main/shared_files/marimo/theme.css').read().decode()}</style>"
    )
    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # **Design and Validation of a Scalable Decentralized Control Architecture for Multi-Zone HVAC Systems**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > **Project by:** Yapa W.S.P.Y.J.C. (E/20/452)

    > **Supervisor:** Dr. D. H. S. Maithripala

    > **Institution:** Department of Mechanical Engineering, University of Peradeniya
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Project Overview
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    This project focuses on designing a scalable, modular, and decentralized control architecture to manage the thermal and operational coupling inherent in multi-zone buildings. By moving away from purely centralized systems, this architecture aims to improve scalability and energy efficiency while maintaining high standards for Indoor Air Quality (IAQ) and human comfort.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Objectives
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    - **Modeling**: Implement xR2C thermal zone modeling derived from 3R2C standards, utilizing an automated pipeline to extract data from EnergyPlus (.idf) files.

    - **Estimation**: Utilize an Augmented Extended Kalman Filter (EKF) to reconstruct hidden thermal mass states and estimate unmodeled disturbances for soft-sensing occupancy.

    - **Control**: Deploy Model Predictive Control (MPC) to manage underactuated systems, prioritizing temperature tracking while maintaining humidity and CO2​ within comfort bounds.

    - **Validation**: Verify the architecture through high-fidelity EnergyPlus simulations and a digitized bench-scale single-zone testbed.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Navigation & Documentation
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    [🏠 Home](https://janithcyapa.github.io/DHCA-Framework/)

    [📑 1.Thermal Zone Modeling](https://janithcyapa.github.io/DHCA-Framework/1.Thermal_Zone_Modeling.html)

    [📑 2.State Estimator Design](https://janithcyapa.github.io/DHCA-Framework/2.State_Estimator_Design.html)

    [📑 3.MPC Design](https://janithcyapa.github.io/DHCA-Framework/3.MPC_Design.html)

    [📑 4.Controllability_Analysis](https://janithcyapa.github.io/DHCA-Framework/4.Controllability_Analysis.html)


    ### Usefull Links

    [🗂️ GitHub Repository](https://github.com/janithcyapa/DHCA-Framework)

    [🗂️ EnergyPlus Util](https://github.com/janithcyapa/energy-plus-utility)

    [🗂️ Test Bench Docs](https://github.com/janithcyapa/MechLabs_AHU)
    """)
    return


if __name__ == "__main__":
    app.run()
