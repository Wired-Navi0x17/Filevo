"""Subject taxonomy for the Semester 3 document-routing system.

Each entry is a *prototype profile* for one course: a human-readable name, a
dense list of academic keywords, and a syllabus-style description.  The
calibrator (:mod:`src.calibrator`) embeds these profiles to build a semantic
"centroid" per subject, so the quality of the routing decision depends
directly on the richness of the text below.

The taxonomy is intentionally data-only: no I/O, no model loading, so it can
be imported cheaply and inspected/tested in isolation.
"""

from __future__ import annotations

import copy

__all__ = ["SUBJECT_TAXONOMY", "get_subject_taxonomy", "subject_labels"]

SUBJECT_TAXONOMY: dict[str, dict] = {
    "CS2000 - Design and Analysis of Algorithms": {
        "code": "CS2000",
        "name": "Design and Analysis of Algorithms",
        "keywords": [
            "algorithm design", "asymptotic analysis", "big-O notation", "time complexity",
            "space complexity", "recurrence relations", "master theorem", "divide and conquer",
            "dynamic programming", "greedy algorithms", "backtracking", "branch and bound",
            "sorting algorithms", "merge sort", "quick sort", "heap sort", "insertion sort",
            "bubble sort", "selection sort", "counting sort", "radix sort", "searching",
            "binary search", "graph algorithms", "breadth first search", "depth first search",
            "Dijkstra", "Bellman-Ford", "Floyd-Warshall", "minimum spanning tree",
            "Kruskal", "Prim", "topological sort", "shortest path", "maximum flow",
            "Ford-Fulkerson", "NP-completeness", "reduction", "P versus NP",
            "approximation algorithms", "amortized analysis", "heap", "priority queue",
            "hashing", "binary search tree", "red-black tree", "B-tree", "trie",
            "string matching", "KMP algorithm", "linear programming", "randomized algorithms",
        ],
        "syllabus": (
            "Design and Analysis of Algorithms studies how to construct efficient "
            "computational procedures and how to reason rigorously about their cost. "
            "Topics include asymptotic notation and growth of functions, recurrence "
            "relations and the master theorem, the divide-and-conquer paradigm, greedy "
            "methods, dynamic programming, and backtracking. Classical sorting and "
            "searching algorithms (merge sort, quick sort, heap sort, binary search) are "
            "analysed for best, average and worst-case time and space complexity. Graph "
            "algorithms cover traversal, shortest paths, minimum spanning trees and "
            "network flow, while complexity theory introduces polynomial reductions, "
            "NP-completeness and approximation. Advanced structures such as heaps, hash "
            "tables and balanced search trees, plus amortized analysis and randomized "
            "algorithms, complete the course."
        ),
    },
    "CS2227 - AI and ML": {
        "code": "CS2227",
        "name": "AI and ML",
        "keywords": [
            "artificial intelligence", "machine learning", "supervised learning",
            "unsupervised learning", "reinforcement learning", "neural networks",
            "deep learning", "gradient descent", "backpropagation", "loss function",
            "feature engineering", "training set", "validation set", "test set",
            "overfitting", "underfitting", "regularization", "bias-variance tradeoff",
            "regression", "linear regression", "logistic regression", "classification",
            "decision tree", "random forest", "support vector machine", "k-nearest neighbours",
            "k-means clustering", "principal component analysis", "naive Bayes",
            "ensemble methods", "boosting", "bagging", "convolutional neural network",
            "recurrent neural network", "transformer", "attention mechanism",
            "embedding", "softmax", "cross-entropy", "model evaluation", "precision",
            "recall", "F1 score", "confusion matrix", "ROC curve", "hyperparameter tuning",
            "search algorithms", "heuristic search", "A-star search", "minimax",
            "knowledge representation", "natural language processing", "computer vision",
            "generative models", "large language models",
        ],
        "syllabus": (
            "AI and ML introduces the foundations of intelligent systems and statistical "
            "learning. It begins with search, knowledge representation and reasoning, then "
            "covers the machine-learning pipeline: data preparation, feature engineering, "
            "model selection and evaluation. Supervised methods include linear and logistic "
            "regression, naive Bayes, k-nearest neighbours, decision trees, support vector "
            "machines and ensemble techniques such as bagging, random forests and boosting. "
            "Unsupervised learning covers k-means clustering, hierarchical clustering and "
            "principal component analysis. Neural networks and deep learning introduce "
            "perceptrons, activation functions, backpropagation, gradient descent, "
            "convolutional and recurrent architectures, attention and transformers. The "
            "course also treats reinforcement learning, natural language processing, "
            "computer vision, generative models and large language models, with emphasis on "
            "generalisation, overfitting, regularization and the bias-variance tradeoff."
        ),
    },
    "CS2235 - Data Science": {
        "code": "CS2235",
        "name": "Data Science",
        "keywords": [
            "data science", "data analysis", "exploratory data analysis", "data wrangling",
            "data cleaning", "data preprocessing", "feature scaling", "missing values",
            "outlier detection", "statistics", "descriptive statistics", "inferential statistics",
            "probability distributions", "hypothesis testing", "p-value", "confidence interval",
            "correlation", "covariance", "regression analysis", "time series analysis",
            "data visualization", "histogram", "scatter plot", "box plot", "dashboard",
            "pandas", "numpy", "matplotlib", "seaborn", "SQL", "relational databases",
            "data warehousing", "ETL pipelines", "big data analytics", "predictive modelling",
            "clustering", "dimensionality reduction", "A/B testing", "sampling", "bias in data",
            "data ethics", "storytelling with data", "reproducible analysis", "Jupyter notebook",
        ],
        "syllabus": (
            "Data Science covers the full lifecycle of turning raw data into insight: "
            "acquisition, cleaning, wrangling, exploration, modelling and communication. "
            "It develops descriptive and inferential statistics, probability distributions, "
            "sampling, hypothesis testing, p-values, confidence intervals and correlation. "
            "Practical tooling includes Python with pandas, numpy, matplotlib and seaborn, "
            "as well as SQL and relational databases, ETL pipelines and data warehousing. "
            "The course emphasises exploratory data analysis, handling missing values and "
            "outliers, feature scaling and dimensionality reduction, regression and "
            "predictive modelling, clustering, time-series analysis and A/B testing. "
            "Visualisation, dashboards, reproducibility, data ethics and storytelling with "
            "data round out the curriculum."
        ),
    },
    "CS2403 - Computer Networks": {
        "code": "CS2403",
        "name": "Computer Networks",
        "keywords": [
            "computer networks", "OSI model", "TCP/IP", "protocol stack", "layered architecture",
            "physical layer", "data link layer", "network layer", "transport layer",
            "application layer", "packet switching", "circuit switching", "routing",
            "IP addressing", "subnetting", "CIDR", "IPv4", "IPv6", "ARP", "ICMP",
            "DHCP", "DNS", "TCP", "UDP", "flow control", "congestion control",
            "sliding window", "error detection", "checksum", "CRC", "Ethernet",
            "Wi-Fi", "CSMA/CD", "MAC address", "switching", "bridging", "VLAN",
            "HTTP", "HTTPS", "FTP", "SMTP", "socket programming", "network security",
            "firewall", "VPN", "quality of service", "network performance", "latency",
            "bandwidth", "throughput", "wireless networks", "mobile networks",
        ],
        "syllabus": (
            "Computer Networks examines how data moves between distributed systems. It "
            "follows the layered model from the physical and data-link layers (framing, "
            "error detection and correction, Ethernet, CSMA/CD, MAC addressing, switching "
            "and bridging) through the network layer (IP addressing, subnetting, CIDR, "
            "routing and forwarding, ARP and ICMP) to the transport layer (TCP and UDP, "
            "connection management, flow control, sliding windows and congestion control). "
            "The application layer covers DNS, DHCP, HTTP, FTP and SMTP together with "
            "socket programming. Ancillary topics include wireless and mobile networks, "
            "quality of service, network performance metrics such as latency, bandwidth "
            "and throughput, and an introduction to network security, firewalls and VPNs."
        ),
    },
    "CS2404 - Internet of Things": {
        "code": "CS2404",
        "name": "Internet of Things",
        "keywords": [
            "internet of things", "IoT architecture", "sensor networks", "actuators",
            "embedded systems", "microcontrollers", "Arduino", "Raspberry Pi", "ESP32",
            "GPIO", "sensing", "telemetry", "edge computing", "fog computing",
            "MQTT", "CoAP", "Zigbee", "LoRaWAN", "Bluetooth Low Energy", "RFID",
            "smart devices", "smart home", "smart city", "industrial IoT", "Industry 4.0",
            "wireless sensor networks", "gateway", "device management", "interoperability",
            "IoT protocols", "low power", "energy harvesting", "real-time systems",
            "cloud IoT integration", "data acquisition", "embedded C", "firmware",
            "sensor fusion", "digital twin", "cyber-physical systems", "wearables",
        ],
        "syllabus": (
            "Internet of Things studies the design and deployment of connected embedded "
            "systems. It covers IoT reference architectures spanning device, edge, fog and "
            "cloud tiers, wireless sensor and actuator networks, microcontrollers and "
            "platforms such as Arduino, Raspberry Pi and ESP32, and the sensing and "
            "actuation chain from GPIO and data acquisition to telemetry. Communication "
            "protocols include MQTT, CoAP, Zigbee, LoRaWAN, Bluetooth Low Energy and RFID, "
            "with attention to low-power operation, energy harvesting and real-time "
            "constraints. Applications span smart homes, smart cities, industrial IoT and "
            "Industry 4.0, wearables and cyber-physical systems. The course also treats "
            "gateways, device management, interoperability, edge analytics and cloud "
            "integration, and introduces digital twins and sensor fusion."
        ),
    },
    "CS2405 - Cyber Security": {
        "code": "CS2405",
        "name": "Cyber Security",
        "keywords": [
            "cyber security", "information security", "cryptography", "encryption",
            "decryption", "symmetric key", "asymmetric key", "public key cryptography",
            "RSA", "AES", "DES", "elliptic curve", "hash function", "SHA", "MD5",
            "digital signature", "message authentication", "HMAC", "key exchange",
            "Diffie-Hellman", "certificates", "PKI", "TLS", "SSL", "authentication",
            "authorization", "access control", "network attacks", "malware", "virus",
            "worm", "trojan", "ransomware", "phishing", "social engineering",
            "denial of service", "DDoS", "man-in-the-middle", "SQL injection",
            "cross-site scripting", "buffer overflow", "intrusion detection",
            "firewalls", "ethical hacking", "penetration testing", "vulnerability",
            "threat modelling", "risk management", "forensics", "zero trust",
            "security policies", "CIA triad", "steganography", "blockchain security",
        ],
        "syllabus": (
            "Cyber Security builds a defensive and adversarial understanding of securing "
            "systems. It introduces the CIA triad and security fundamentals before covering "
            "cryptography in depth: classical ciphers, symmetric encryption (DES, AES), "
            "asymmetric and public-key cryptography (RSA, elliptic curves), hash functions "
            "(SHA, MD5), message authentication codes, digital signatures, key exchange and "
            "the Diffie-Hellman protocol. It then treats network and application attacks "
            "such as malware, worms, trojans, ransomware, phishing and social engineering, "
            "denial-of-service and DDoS, man-in-the-middle, SQL injection, cross-site "
            "scripting and buffer overflows. Defences include firewalls, intrusion detection, "
            "PKI and TLS, authentication and access control, threat modelling, risk "
            "management, digital forensics, penetration testing and the zero-trust model."
        ),
    },
    "CS2500 - Cloud Computing and Big Data": {
        "code": "CS2500",
        "name": "Cloud Computing and Big Data",
        "keywords": [
            "cloud computing", "big data", "virtualization", "hypervisor", "virtual machines",
            "containers", "Docker", "Kubernetes", "serverless", "microservices",
            "IaaS", "PaaS", "SaaS", "cloud deployment models", "public cloud",
            "private cloud", "hybrid cloud", "elasticity", "scalability", "load balancing",
            "distributed systems", "Hadoop", "MapReduce", "HDFS", "Spark", "Hive",
            "NoSQL", "distributed storage", "data lake", "data warehouse", "stream processing",
            "Kafka", "batch processing", "cluster computing", "fault tolerance",
            "replication", "consistency", "CAP theorem", "data partitioning", "sharding",
            "resource scheduling", "cost optimization", "cloud security", "multi-tenancy",
            "edge computing", "data parallel analytics",
        ],
        "syllabus": (
            "Cloud Computing and Big Data examines how large-scale systems are provisioned "
            "and how massive datasets are processed. It covers cloud service and deployment "
            "models (IaaS, PaaS, SaaS; public, private and hybrid), virtualization and "
            "hypervisors, containers with Docker and orchestration with Kubernetes, "
            "serverless computing and microservices, plus elasticity, scalability and load "
            "balancing. The big-data half treats distributed storage and computation: the "
            "Hadoop ecosystem with HDFS and MapReduce, Apache Spark, Hive, stream processing "
            "with Kafka, NoSQL stores, data lakes and warehouses, batch versus stream "
            "processing and cluster computing. Systems themes include fault tolerance, "
            "replication, consistency, the CAP theorem, partitioning and sharding, resource "
            "scheduling, multi-tenancy and cloud security and cost optimisation."
        ),
    },
    "CS2806 - Calculus": {
        "code": "CS2806",
        "name": "Calculus",
        "keywords": [
            "calculus", "limits", "continuity", "derivative", "differentiation",
            "differential calculus", "integral", "integration", "integral calculus",
            "definite integral", "indefinite integral", "Riemann sum", "antiderivative",
            "fundamental theorem of calculus", "chain rule", "product rule", "quotient rule",
            "implicit differentiation", "related rates", "critical point", "maxima",
            "minima", "optimization", "concavity", "inflection point", "mean value theorem",
            "Rolle's theorem", "L'Hopital's rule", "Taylor series", "Maclaurin series",
            "sequences", "series", "convergence", "divergence", "partial derivatives",
            "gradient", "multiple integrals", "double integral", "parametric equations",
            "polar coordinates", "differential equations", "area under a curve",
            "volume of revolution", "tangent line", "rate of change", "extrema",
        ],
        "syllabus": (
            "Calculus develops the mathematics of change and accumulation. It begins with "
            "limits, continuity and the formal definition of the derivative, then builds "
            "differential calculus: differentiation rules (power, product, quotient and "
            "chain rule), implicit differentiation, related rates, and the analysis of "
            "functions through critical points, maxima and minima, concavity and inflection. "
            "The mean value theorem, Rolle's theorem and L'Hopital's rule provide the key "
            "theorems used for optimisation. Integral calculus introduces antiderivatives, "
            "Riemann sums, definite and indefinite integrals, the fundamental theorem of "
            "calculus, area under a curve and volumes of revolution. The course extends to "
            "sequences and series with convergence tests, Taylor and Maclaurin series, "
            "partial derivatives, gradients, multiple and double integrals, parametric and "
            "polar coordinates, and an introduction to differential equations."
        ),
    },
}


def get_subject_taxonomy(custom_taxonomy: dict[str, dict] | None = None) -> dict[str, dict]:
    """Return a fresh copy of the subject taxonomy or user-provided taxonomy."""
    base = custom_taxonomy if custom_taxonomy is not None else SUBJECT_TAXONOMY
    return {
        k: {
            "code": v.get("code", ""),
            "name": v.get("name", ""),
            "keywords": list(v.get("keywords", [])),
            "syllabus": v.get("syllabus", ""),
        }
        for k, v in base.items()
    }


def subject_labels(custom_taxonomy: dict[str, dict] | None = None) -> list[str]:
    """Return the ordered list of subject labels."""
    if custom_taxonomy:
        return list(custom_taxonomy.keys())
    return list(SUBJECT_TAXONOMY.keys())


def discover_target_taxonomy(target_root_path: str) -> dict[str, dict]:
    """Dynamically build a taxonomy from subfolders existing in target_root.
    
    If subfolders match known taxonomy keys or codes, merge their rich keywords.
    Otherwise, derive keywords and prototypes from the folder name.
    """
    from pathlib import Path
    root = Path(target_root_path).expanduser().resolve()
    if not root.is_dir():
        return get_subject_taxonomy()

    subdirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not subdirs:
        return get_subject_taxonomy()

    discovered: dict[str, dict] = {}
    known = get_subject_taxonomy()

    for d in sorted(subdirs, key=lambda p: p.name.lower()):
        folder_name = d.name
        # Match with known taxonomy if possible
        matched_key = None
        for k, info in known.items():
            if folder_name.lower() == k.lower() or folder_name.lower() == info.get("name", "").lower() or folder_name.lower() == info.get("code", "").lower():
                matched_key = k
                break

        if matched_key:
            entry = copy.deepcopy(known[matched_key])
            discovered[folder_name] = entry
        else:
            # Generate prototype profile from folder name
            clean_name = folder_name.replace("-", " ").replace("_", " ")
            parts = [w for w in clean_name.split() if w.strip()]
            keywords = [clean_name.lower()] + [p.lower() for p in parts if len(p) > 2]
            discovered[folder_name] = {
                "code": parts[0] if parts and any(c.isdigit() for c in parts[0]) else "",
                "name": clean_name,
                "keywords": keywords,
                "syllabus": f"Documents, coursework, materials and references concerning {clean_name}.",
            }

    return discovered if discovered else get_subject_taxonomy()

