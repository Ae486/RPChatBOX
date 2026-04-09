import 'package:chatboxapp/adapters/ai_provider.dart';
import 'package:chatboxapp/adapters/hybrid_langchain_provider.dart';
import 'package:chatboxapp/adapters/proxy_openai_provider.dart';
import 'package:chatboxapp/models/backend_mode.dart';
import 'package:chatboxapp/models/provider_config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late bool originalUseLangChain;
  late bool originalUseHybridLangChain;
  late bool originalPythonBackendEnabled;

  ProviderConfig buildConfig(BackendMode backendMode) {
    return ProviderConfig(
      id: 'provider-1',
      name: 'Test Provider',
      type: ProviderType.openai,
      apiUrl: 'https://api.example.com/v1',
      apiKey: 'sk-test',
      backendMode: backendMode,
    );
  }

  setUp(() {
    originalUseLangChain = ProviderFactory.useLangChain;
    originalUseHybridLangChain = ProviderFactory.useHybridLangChain;
    originalPythonBackendEnabled = ProviderFactory.pythonBackendEnabled;

    ProviderFactory.useLangChain = false;
    ProviderFactory.useHybridLangChain = true;
    ProviderFactory.pythonBackendEnabled = false;
  });

  tearDown(() {
    ProviderFactory.useLangChain = originalUseLangChain;
    ProviderFactory.useHybridLangChain = originalUseHybridLangChain;
    ProviderFactory.pythonBackendEnabled = originalPythonBackendEnabled;
  });

  group('ProviderFactory.createProviderWithRouting', () {
    test('returns HybridLangChainProvider when backend switch is off', () {
      for (final mode in BackendMode.values) {
        final provider = ProviderFactory.createProviderWithRouting(buildConfig(mode));
        expect(provider, isA<HybridLangChainProvider>());
      }
    });

    test('returns ProxyOpenAIProvider when backend switch is on', () {
      ProviderFactory.pythonBackendEnabled = true;

      for (final mode in BackendMode.values) {
        final provider = ProviderFactory.createProviderWithRouting(buildConfig(mode));
        expect(provider, isA<ProxyOpenAIProvider>());
      }
    });

    test('currently ignores backendMode when backend switch is on', () {
      ProviderFactory.pythonBackendEnabled = true;

      final directProvider = ProviderFactory.createProviderWithRouting(
        buildConfig(BackendMode.direct),
      );
      final proxyProvider = ProviderFactory.createProviderWithRouting(
        buildConfig(BackendMode.proxy),
      );
      final autoProvider = ProviderFactory.createProviderWithRouting(
        buildConfig(BackendMode.auto),
      );

      expect(directProvider.runtimeType, equals(ProxyOpenAIProvider));
      expect(proxyProvider.runtimeType, equals(ProxyOpenAIProvider));
      expect(autoProvider.runtimeType, equals(ProxyOpenAIProvider));
    });

    test('returns HybridLangChainProvider when forceDirect is set', () {
      ProviderFactory.pythonBackendEnabled = true;

      for (final mode in BackendMode.values) {
        final provider = ProviderFactory.createProviderWithRouting(
          buildConfig(mode),
          forceDirect: true,
        );
        expect(provider, isA<HybridLangChainProvider>());
      }
    });
  });
}
