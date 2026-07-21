# Increment 5 report

Version: 0.5.0
Theme: Azure-native evidence storage and Microsoft Defender for Storage

The application now supports a secure cloud evidence lifecycle. Files uploaded to Azure are marked pending and cannot be downloaded until Defender reports a clean result. Scan status can arrive through Event Grid or be refreshed from blob index tags. Clean files are delivered using short-lived user-delegation SAS URLs. Malicious and failed scans remain blocked.

Local development continues to use the existing protected filesystem and ClamAV-compatible scanner, keeping the test suite independent of live Azure credentials.
