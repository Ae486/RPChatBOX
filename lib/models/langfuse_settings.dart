class LangfuseSettingsStatus {
  final bool enabled;
  final bool configured;
  final bool serviceEnabled;
  final bool sdkAvailable;
  final String statusReason;
  final String source;
  final String? publicKey;
  final bool hasSecretKey;
  final String? baseUrl;
  final String? dashboardUrl;
  final String? environment;
  final String? release;
  final double? sampleRate;
  final bool debug;
  final String? configPath;

  const LangfuseSettingsStatus({
    required this.enabled,
    required this.configured,
    required this.serviceEnabled,
    required this.sdkAvailable,
    required this.statusReason,
    required this.source,
    required this.publicKey,
    required this.hasSecretKey,
    required this.baseUrl,
    required this.dashboardUrl,
    required this.environment,
    required this.release,
    required this.sampleRate,
    required this.debug,
    required this.configPath,
  });

  factory LangfuseSettingsStatus.fromJson(Map<String, dynamic> json) {
    return LangfuseSettingsStatus(
      enabled: json['enabled'] as bool? ?? false,
      configured: json['configured'] as bool? ?? false,
      serviceEnabled: json['service_enabled'] as bool? ?? false,
      sdkAvailable: json['sdk_available'] as bool? ?? false,
      statusReason: json['status_reason'] as String? ?? 'disabled',
      source: json['source'] as String? ?? 'env',
      publicKey: json['public_key'] as String?,
      hasSecretKey: json['has_secret_key'] as bool? ?? false,
      baseUrl: json['base_url'] as String?,
      dashboardUrl: json['dashboard_url'] as String?,
      environment: json['environment'] as String?,
      release: json['release'] as String?,
      sampleRate: (json['sample_rate'] as num?)?.toDouble(),
      debug: json['debug'] as bool? ?? false,
      configPath: json['config_path'] as String?,
    );
  }

  LangfuseSettingsStatus copyWith({
    bool? enabled,
    bool? configured,
    bool? serviceEnabled,
    bool? sdkAvailable,
    String? statusReason,
    String? source,
    String? publicKey,
    bool? hasSecretKey,
    String? baseUrl,
    String? dashboardUrl,
    String? environment,
    String? release,
    double? sampleRate,
    bool? debug,
    String? configPath,
  }) {
    return LangfuseSettingsStatus(
      enabled: enabled ?? this.enabled,
      configured: configured ?? this.configured,
      serviceEnabled: serviceEnabled ?? this.serviceEnabled,
      sdkAvailable: sdkAvailable ?? this.sdkAvailable,
      statusReason: statusReason ?? this.statusReason,
      source: source ?? this.source,
      publicKey: publicKey ?? this.publicKey,
      hasSecretKey: hasSecretKey ?? this.hasSecretKey,
      baseUrl: baseUrl ?? this.baseUrl,
      dashboardUrl: dashboardUrl ?? this.dashboardUrl,
      environment: environment ?? this.environment,
      release: release ?? this.release,
      sampleRate: sampleRate ?? this.sampleRate,
      debug: debug ?? this.debug,
      configPath: configPath ?? this.configPath,
    );
  }
}

class LangfuseSettingsUpdateRequest {
  final bool enabled;
  final String? publicKey;
  final String? secretKey;
  final bool clearSecretKey;
  final String? baseUrl;
  final String? environment;
  final String? release;
  final double? sampleRate;
  final bool debug;

  const LangfuseSettingsUpdateRequest({
    required this.enabled,
    this.publicKey,
    this.secretKey,
    this.clearSecretKey = false,
    this.baseUrl,
    this.environment,
    this.release,
    this.sampleRate,
    this.debug = false,
  });

  Map<String, dynamic> toJson() {
    return {
      'enabled': enabled,
      'public_key': publicKey,
      'secret_key': secretKey,
      'clear_secret_key': clearSecretKey,
      'base_url': baseUrl,
      'environment': environment,
      'release': release,
      'sample_rate': sampleRate,
      'debug': debug,
    };
  }
}
