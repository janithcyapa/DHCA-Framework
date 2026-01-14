# Decentralized HVAC Control Architecture (FYP)

![Status](https://img.shields.io/badge/Status-Development-yellow) ![License](https://img.shields.io/badge/License-MIT-blue)

## 📄 Abstract
This repository contains the source code and simulation models for my Final Year Project: **A Decentralized Control Architecture for Multi-Zone HVAC Systems**. Unlike traditional centralized systems, this architecture allows individual zones to regulate their own parameters while coordinating energy consumption, leading to higher fault tolerance and scalability.

## 🚀 Key Features
* **Decentralized Logic:** Each zone operates as an independent node.
* **Energy Optimization:** Minimizes power consumption while maintaining thermal comfort (PMV/PPD).
* **Scalability:** Easily add or remove zones without reconfiguring a central server.
* **Fault Tolerance:** System continues to function even if individual zone controllers fail.

## 🛠️ Tech Stack
* **Language:** Python / C++ 
* **Simulation:** EnergyPlus v25.1
* **Hardware (Optional):** ESP32 / Raspberry Pi 

## 📂 Project Structure
* `/src`: Main control algorithms.
* `/simulations`: Simulation files and datasets.
* `/docs`: System architecture diagrams and thesis drafts.
