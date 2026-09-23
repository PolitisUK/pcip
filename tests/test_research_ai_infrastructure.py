from pathlib import Path


def test_research_ai_infrastructure_is_dedicated_private_and_identity_only():
    bicep = Path("infra/research-ai.bicep").read_text(encoding="utf-8")

    assert "kind: 'OpenAI'" in bicep
    assert "publicNetworkAccess: 'Disabled'" in bicep
    assert "defaultAction: 'Deny'" in bicep
    assert "disableLocalAuth: true" in bicep
    assert "Microsoft.Network/privateEndpoints" in bicep
    assert "privatelink.openai.azure.com" in bicep
    assert "Microsoft.Web/sites/networkConfig" in bicep
    assert (
        "Cognitive Services OpenAI User" not in bicep
    )  # role is fixed by immutable ID
    assert "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd" in bicep
    assert "Contributor" not in bicep
    assert "name: '${environmentName}-research-ai-vnet-link'" in bicep
    assert "name: 'research-ai-vnet-link'" not in bicep

    private_endpoint = bicep.partition(
        "resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01'"
    )[2].partition("\n}\n")[0]
    assert "location: resourceGroup().location" in private_endpoint
    assert "location: aiLocation" not in private_endpoint


def test_research_ai_model_and_processing_boundary_are_governed():
    bicep = Path("infra/research-ai.bicep").read_text(encoding="utf-8")

    assert "name: 'DataZoneStandard'" in bicep
    assert "name: 'gpt-4.1-mini'" in bicep
    assert "version: '2025-04-14'" in bicep
    assert "versionUpgradeOption: 'NoAutoUpgrade'" in bicep
    assert "GlobalStandard" not in bicep


def test_research_ai_diagnostics_exclude_request_response_content():
    bicep = Path("infra/research-ai.bicep").read_text(encoding="utf-8")

    assert "category: 'Audit'" in bicep
    assert "category: 'AzureOpenAIRequestUsage'" in bicep
    assert "RequestResponse" not in bicep


def test_research_ai_infrastructure_does_not_activate_application_features():
    bicep = Path("infra/research-ai.bicep").read_text(encoding="utf-8")

    assert "RESEARCH_INTELLIGENCE_AI_CODING_ENABLED" not in bicep
    assert "RESEARCH_INTELLIGENCE_SEMANTIC_SEARCH_ENABLED" not in bicep
    assert "AZURE_OPENAI_API_KEY" not in bicep
