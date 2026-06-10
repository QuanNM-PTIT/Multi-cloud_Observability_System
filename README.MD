
# Multi-Cloud VM Observability System Using OpenTelemetry Collector Agent

> Student: B25CHHT048 - Nguyễn Mạnh Quân
> Supervisor: TS. Đặng Ngọc Hùng
> Course: Graduation Internship - Master Program, PTIT

## 1. Project Overview

This project aims to build a **multi-cloud observability system** for virtual machines running across different cloud providers, including **Viettel IDC, AWS, Google Cloud, Microsoft Azure**, and equivalent private cloud environments.

Instead of using a separate monitoring tool for each cloud platform, the proposed system uses the **OpenTelemetry Collector Agent** as a unified telemetry collection layer. The agent is installed directly on each VM to collect important operational data such as CPU, memory, disk, filesystem, network traffic, and server availability status.

After being collected, the telemetry data is sent to a centralized monitoring system for storage, visualization, and alerting. Within the 4-week internship scope, the project focuses on building a **Proof of Concept (PoC) / Minimum Viable Product (MVP)** that can demonstrate an end-to-end monitoring flow.

```text
VMs from Multiple Cloud Providers
        |
        | OpenTelemetry Collector Agent
        v
Telemetry Pipeline
        |
        v
VictoriaMetrics / Metric Storage
        |
        +------------------> Grafana Dashboard
        |
        +------------------> vmalert
                                |
                                v
                        vmalertmanager
                                |
                                v
                Email / Webhook / Notification Channel

```

## 2. Project Objectives

The main objective of this project is to build a VM monitoring system that can work across multiple cloud platforms. The system collects metrics using the OpenTelemetry standard and visualizes them through a centralized dashboard.

Specific objectives include:

-   Install and configure the **OpenTelemetry Collector Agent** on Linux VMs.
    
-   Collect basic system metrics such as CPU, memory, disk, filesystem, and network usage.
    
-   Send metrics from the agent to a centralized metric storage system.
    
-   Use **Grafana** to build VM monitoring dashboards.
    
-   Use **vmalert** to define and evaluate alerting rules.
    
-   Use **vmalertmanager** to receive, manage, group, and route alerts.
    
-   Test the system on multiple VMs or different cloud environments if available.
    
-   Complete technical documentation, deployment instructions, and the final internship report.

## 3. Project Scope

Within the 4-week implementation period, the project focuses on the core observability workflow. Metrics are prioritized over logs and traces to ensure that a working MVP can be completed within the available time.

### 3.1 In-Scope MVP Features

-   Monitor Linux VMs.
    
-   Collect system metrics using the OpenTelemetry Collector Agent.
    
-   Send metrics to VictoriaMetrics or an equivalent metric storage backend.
    
-   Display monitoring data on Grafana dashboards.
    
-   Configure alerting rules using vmalert.
    
-   Manage alerts using vmalertmanager.
    
-   Test abnormal scenarios such as high CPU usage, high memory usage, disk almost full, and stopped agents.
    

### 3.2 Out-of-Scope Features

The following features are not included in the MVP and may be developed later:

-   Centralized log collection.
    
-   Distributed tracing.
    
-   Full support for Windows VMs.
    
-   Agent management portal.
    
-   Automatic agent installation through an API.
    
-   Advanced notification integrations such as Email, Telegram, Slack, and webhook routing.
    
-   AI-based anomaly detection and AIOps features.


## 4. Technology Stack

The project uses an observability-oriented technology stack designed to collect, store, visualize, and alert on VM-level monitoring data across multiple cloud environments.

### 4.1 Telemetry Collection Layer

-   **OpenTelemetry Collector Contrib**
    
    -   Acts as the main telemetry collection agent installed on each monitored VM.
        
    -   Collects system-level metrics such as CPU, memory, disk, filesystem, and network usage.
        
    -   Provides a vendor-neutral collection layer, allowing the system to work across different cloud providers without depending on provider-specific monitoring tools.
        
    -   The Contrib distribution is selected because it includes more receivers, processors, and exporters than the core OpenTelemetry Collector.
        
-   **Host Metrics Receiver**
    
    -   Used inside the OpenTelemetry Collector configuration to collect infrastructure metrics from the VM.
        
    -   Collects metrics from the operating system, including CPU load, memory usage, disk I/O, filesystem usage, network traffic, and system load.
        
    -   Suitable for VM monitoring because it does not require application-level instrumentation.
        
-   **Resource Detection Processor**
    
    -   Adds metadata to collected metrics.
        
    -   Used to enrich telemetry data with VM-related information such as hostname, operating system, cloud provider, region, instance ID, and environment.
        
    -   Helps distinguish metrics from different VMs and cloud platforms in Grafana dashboards and alerting rules.
        
-   **Batch Processor**
    
    -   Groups collected metrics before exporting them to the backend.
        
    -   Reduces the number of outgoing requests from the agent to the metric storage system.
        
    -   Improves performance and makes the telemetry pipeline more efficient.
        
-   **Memory Limiter Processor**
    
    -   Prevents the OpenTelemetry Collector Agent from consuming too much memory on small VM instances.
        
    -   Important when monitoring low-resource VMs such as 2 CPU / 2 GB RAM instances.
        
    -   Helps maintain agent stability during high metric volume or temporary backend connectivity issues.
        
-   **Prometheus Remote Write Exporter**
    
    -   Sends metrics from the OpenTelemetry Collector Agent to a Prometheus-compatible time-series backend.
        
    -   Used to export data to VictoriaMetrics.
        
    -   Provides a standard and widely supported metric export mechanism.


### 4.2 Metric Storage Layer

-   **VictoriaMetrics**
    
    -   Used as the centralized time-series database for storing VM metrics.
        
    -   Receives metrics from OpenTelemetry Collector Agents through the Prometheus Remote Write protocol.
        
    -   Provides high-performance metric ingestion and efficient long-term storage.
        
    -   Compatible with PromQL, allowing Grafana and vmalert to query metrics in a Prometheus-like way.
        
    -   In the MVP phase, a single-node VictoriaMetrics deployment is sufficient. In future production scenarios, it can be extended to a clustered deployment.
        
-   **Prometheus-Compatible Query API**
    
    -   Allows Grafana and vmalert to query VictoriaMetrics using PromQL-compatible expressions.
        
    -   Makes the monitoring stack easier to integrate because many observability tools already support Prometheus-style queries.


### 4.3 Visualization Layer

-   **Grafana**
    
    -   Used as the main visualization tool for monitoring dashboards.
        
    -   Connects to VictoriaMetrics as a Prometheus-compatible datasource.
        
    -   Displays VM metrics in charts, tables, gauges, and status panels.
        
    -   Provides a centralized interface for observing VM health across multiple cloud providers.
        
-   **Grafana Dashboard**
    
    -   Used to present key monitoring indicators in a clear and operationally useful format.
        
    -   The dashboard includes panels for:
        
        -   Total monitored VMs.
            
        -   CPU usage per VM.
            
        -   Memory usage per VM.
            
        -   Disk and filesystem usage.
            
        -   Network receive/transmit traffic.
            
        -   VM availability status.
            
        -   OpenTelemetry Agent status.
            
    -   Dashboard variables can be added to filter data by cloud provider, region, environment, or VM hostname.
        
-   **Grafana Datasource Configuration**
    
    -   Configures Grafana to read metrics from VictoriaMetrics.
        
    -   Uses the Prometheus datasource type because VictoriaMetrics supports Prometheus-compatible APIs.
        
    -   Enables dashboard panels to query metrics using PromQL-style expressions.

### 4.4 Alerting Layer

-   **vmalert**
    
    -   Used as the alert rule evaluation engine.
        
    -   Periodically queries VictoriaMetrics and evaluates predefined alerting rules.
        
    -   Detects abnormal VM conditions such as high CPU usage, high memory usage, disk almost full, VM unavailable, or stopped agent.
        
    -   Sends triggered alerts to vmalertmanager or an Alertmanager-compatible service.
        
-   **Alert Rules**
    
    -   Define the conditions that determine when an alert should be triggered.
        
    -   Example alert rules include:
        
        -   CPU usage greater than 80% for 5 minutes.
            
        -   Memory usage greater than 85% for 5 minutes.
            
        -   Disk usage greater than 90%.
            
        -   VM stops sending metrics.
            
        -   OpenTelemetry Collector Agent becomes unavailable.
            
    -   Alert rules help convert raw monitoring data into actionable operational signals.
        
-   **vmalertmanager / Alertmanager-Compatible Service**
    
    -   Receives alerts from vmalert.
        
    -   Groups, deduplicates, and routes alerts to notification channels.
        
    -   Helps prevent duplicate alerts and alert noise.
        
    -   Can be integrated with email, webhook, Telegram, Slack, or other incident notification systems.

### 4.5 Notification Layer

-   **Webhook**
    
    -   Used as a flexible notification mechanism for sending alerts to external systems.
        
    -   Suitable for integrating with custom backend services, chat tools, or incident management platforms.
        
-   **Email Notification**
    
    -   Can be used to send alert messages to administrators or operators.
        
    -   Suitable for basic alert delivery in the MVP phase.
        
-   **Telegram / Slack Notification**
    
    -   Optional notification channels for future enhancement.
        
    -   Useful for real-time operational alerts and team collaboration.

### 4.6 Cloud Infrastructure Layer

-   **Viettel IDC Cloud VM**
    
    -   One of the target cloud environments for testing the monitoring agent.
        
    -   Represents the local cloud provider use case.
        
    -   Used to validate whether the observability system can monitor VMs outside global public cloud platforms.
        
-   **AWS EC2**
    
    -   Represents a public cloud VM environment.
        
    -   Can be used to test multi-cloud compatibility.
        
    -   VM metadata such as region, instance ID, and cloud provider can be attached to metrics for filtering and dashboard grouping.

- **DigitalOcean Droplets**
    
    -   Represents a lightweight public cloud VM environment.
        
    -   Suitable for quickly testing the OpenTelemetry Collector Agent because DigitalOcean Droplets are simple to provision and operate.
        
    -   VM metadata such as droplet name, region, operating system, and environment can be attached to metrics for dashboard filtering and alert grouping.

### 4.7 Security and Configuration Layer

-   **Agent Token**
    
    -   Used to identify and authenticate the agent when sending data to the central system.
        
    -   Helps ensure that only authorized VMs can send metrics.
        
    -   Can be extended in future versions to support tenant-based isolation.
        
-   **TLS / HTTPS**
    
    -   Used to secure communication between agents and the central observability backend.
        
    -   Prevents telemetry data from being transmitted in plaintext.
        
    -   Recommended for production deployments.
        
-   **VM Metadata Labels**
    
    -   Used to classify and filter metrics.
        
    -   Common labels include:
        
        -   `cloud_provider`
            
        -   `region`
            
        -   `instance_id`
            
        -   `hostname`
            
        -   `environment`
            
        -   `customer_id`
            
    -   These labels make dashboards and alert rules more meaningful in a multi-cloud environment.
        
-   **Configuration Files**
    
    -   Used to manage OpenTelemetry Collector, VictoriaMetrics, Grafana, and vmalert settings.
        
    -   Version-controlled configuration files help make the deployment reproducible and easier to maintain.

## 5. Implementation Plan

### Week 1: Architecture Design and Core Platform Setup

**Objective:** Finalize the system architecture, prepare the deployment environment, and set up the core monitoring components.

**Main tasks:**

-   Define the MVP scope for the observability system.
    
-   Design the overall architecture for multi-cloud VM monitoring.
    
-   Prepare test VMs on Viettel IDC, private cloud, or public cloud environments.
    
-   Set up VictoriaMetrics, Grafana, vmalert, and vmalertmanager.
    
-   Define the list of metrics to collect in the MVP.
    
-   Prepare the initial project directory structure and configuration files.
    

**Expected output:**

-   High-level system architecture diagram.
    
-   Central monitoring environment with the main components installed.
    
-   Initial project structure.
    
-   End-to-end data flow description.
    

### Week 2: OpenTelemetry Collector Agent Deployment on VMs

**Objective:** Install the agent on VMs and collect real system metrics from the servers.

**Main tasks:**

-   Install OpenTelemetry Collector Contrib on Linux VMs.
    
-   Configure the agent to run as a systemd service.
    
-   Build the collector configuration file with receivers, processors, and exporters.
    
-   Standardize VM metadata such as hostname, cloud provider, region, instance ID, and environment.
    
-   Verify that metrics are successfully sent to the metric storage backend.
    
-   Extend testing to another VM or cloud environment if available.
    

**Expected output:**

-   OpenTelemetry Collector Agent running stably on at least one VM.
    
-   Complete collector configuration file for the MVP.
    
-   CPU, memory, disk, filesystem, and network metrics successfully sent to metric storage.
    
-   Manual agent installation guide.
    

### Week 3: Grafana Dashboard and Alerting Configuration

**Objective:** Visualize metric data and complete the basic alerting workflow.

**Main tasks:**

-   Configure the Grafana datasource to connect to VictoriaMetrics.
    
-   Build an overview dashboard for multi-cloud VM monitoring.
    
-   Design dashboard panels for CPU, memory, disk, filesystem, network, VM status, and agent status.
    
-   Configure vmalert to query metrics from VictoriaMetrics.
    
-   Build alerting rules for high CPU, high memory, disk almost full, VM unavailable, and agent stopped.
    
-   Configure vmalert to send alerts to vmalertmanager.
    
-   Trigger abnormal scenarios on the VM to test alert behavior.
    

**Expected output:**

-   Grafana dashboard displaying real VM metrics.
    
-   Basic alerting rules running through vmalert.
    
-   vmalertmanager receiving alerts from vmalert.
    
-   Screenshots of dashboard panels and active alerts.
    

### Week 4: End-to-End Testing, Documentation, and Final Report

**Objective:** Test the whole system, finalize documentation, and complete the internship deliverables.

**Main tasks:**

-   Perform end-to-end testing for the complete workflow.
    
-   Execute test scenarios such as normal VM status, high CPU, high memory, disk almost full, stopped agent, VM restart, and adding a new VM.
    
-   Review and refine agent configuration, dashboards, and alerting rules.
    
-   Prepare deployment documentation.
    
-   Complete the internship report.
    
-   Prepare the demo and presentation materials.

**Expected output:**

-   Complete PoC/MVP system.
    
-   Final internship report.
    
-   Screenshots of dashboards, alerts, and test results.
    
-   Deployment and operation documentation.
    
-   Final demo scenario.