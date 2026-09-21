import 'package:flutter/material.dart';

const citizenBlue = Color(0xFF174A8B);
const citizenBrightBlue = Color(0xFF215BB3);
const citizenOrange = Color(0xFF9A4B20);
const citizenInk = Color(0xFF172033);
const citizenMuted = Color(0xFF536278);
const citizenCanvas = Color(0xFFF3F6FA);
const citizenBorder = Color(0xFFD4DDEA);

ThemeData buildParticipantTheme() {
  const scheme = ColorScheme.light(
    primary: citizenBlue,
    onPrimary: Colors.white,
    primaryContainer: Color(0xFFDCE9FC),
    onPrimaryContainer: Color(0xFF082F61),
    secondary: citizenOrange,
    onSecondary: Colors.white,
    secondaryContainer: Color(0xFFFFE4D4),
    onSecondaryContainer: Color(0xFF49200A),
    surface: Colors.white,
    onSurface: citizenInk,
    error: Color(0xFFB42318),
    onError: Colors.white,
    outline: Color(0xFF69778D),
    outlineVariant: citizenBorder,
  );
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: citizenCanvas,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    visualDensity: VisualDensity.standard,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: citizenInk,
      displayColor: citizenInk,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.white,
      foregroundColor: citizenInk,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: citizenInk,
        fontSize: 20,
        fontWeight: FontWeight.w700,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: citizenBorder),
      ),
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: citizenBorder),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 52),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 52),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(48, 48),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    listTileTheme: const ListTileThemeData(
      minTileHeight: 64,
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      titleTextStyle: TextStyle(
        color: citizenInk,
        fontSize: 16,
        fontWeight: FontWeight.w700,
      ),
      subtitleTextStyle: TextStyle(color: citizenMuted, fontSize: 14),
    ),
    dividerTheme: const DividerThemeData(color: citizenBorder),
  );
}

class ActivityPresentation {
  const ActivityPresentation(this.icon, this.label);

  final IconData icon;
  final String label;
}

ActivityPresentation activityPresentation(String? type) => switch (type) {
  'short_text' || 'long_text' => const ActivityPresentation(
    Icons.subject_outlined,
    'Text response',
  ),
  'message' => const ActivityPresentation(Icons.chat_outlined, 'Message'),
  'photo' => const ActivityPresentation(Icons.photo_camera_outlined, 'Photo'),
  'audio' => const ActivityPresentation(Icons.mic_none_outlined, 'Voice'),
  'video' => const ActivityPresentation(Icons.videocam_outlined, 'Video'),
  'gps' => const ActivityPresentation(Icons.location_on_outlined, 'Location'),
  'ranking' => const ActivityPresentation(
    Icons.format_list_numbered,
    'Ranking',
  ),
  'rating' => const ActivityPresentation(Icons.star_outline, 'Rating'),
  'slider' => const ActivityPresentation(Icons.tune, 'Scale'),
  'single_choice' || 'multiple_choice' => const ActivityPresentation(
    Icons.checklist_outlined,
    'Choice',
  ),
  'file' => const ActivityPresentation(Icons.attach_file, 'Document'),
  _ => const ActivityPresentation(Icons.assignment_outlined, 'Activity'),
};

class ActivityIcon extends StatelessWidget {
  const ActivityIcon({super.key, required this.type});

  final String? type;

  @override
  Widget build(BuildContext context) {
    final presentation = activityPresentation(type);
    return ExcludeSemantics(
      child: Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Icon(
          presentation.icon,
          color: Theme.of(context).colorScheme.onPrimaryContainer,
        ),
      ),
    );
  }
}

class ActivityHeader extends StatelessWidget {
  const ActivityHeader({
    super.key,
    required this.type,
    required this.prompt,
    this.status,
  });

  final String? type;
  final String prompt;
  final String? status;

  @override
  Widget build(BuildContext context) {
    final presentation = activityPresentation(type);
    return Semantics(
      container: true,
      label:
          '${presentation.label}. $prompt${status == null ? '' : '. Status: $status'}',
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ActivityIcon(type: type),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ExcludeSemantics(
                      child: Text(
                        presentation.label,
                        style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    ExcludeSemantics(child: Text(prompt)),
                    if (status != null) ...[
                      const SizedBox(height: 10),
                      ExcludeSemantics(
                        child: Text(
                          status!,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.label, required this.icon});

  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Status: $label',
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ExcludeSemantics(child: Icon(icon, size: 16)),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    ),
  );
}
