package service

import (
	"log/slog"
	"strings"

	"github.com/Wei-Shaw/sub2api/internal/auditcontent"
)

func ExtractContentModerationText(protocol string, body []byte) string {
	return ExtractContentModerationInput(protocol, body).Text
}

func ExtractContentModerationInput(protocol string, body []byte) ContentModerationInput {
	input, _, _, _ := extractContentModerationInput(protocol, body)
	return input
}

// extractContentModerationKeywordText mirrors the semantic scan: inbound
// <system-reminder> markup is not a trust boundary, so the local keyword
// matcher inspects the same current direct-user text. It skips the rune
// budget on purpose: a client-supplied reminder block must never be able to
// push a blocked keyword past the truncation point and hide it.
func extractContentModerationKeywordText(protocol string, body []byte) string {
	input, _, _, _ := extractContentModerationInputWithBudget(protocol, body, false)
	return input.Text
}

func extractContentModerationInput(protocol string, body []byte) (ContentModerationInput, bool, []auditcontent.IncompleteReason, error) {
	return extractContentModerationInputWithBudget(protocol, body, true)
}

func extractContentModerationInputWithBudget(protocol string, body []byte, applyRuneBudget bool) (ContentModerationInput, bool, []auditcontent.IncompleteReason, error) {
	document, err := auditcontent.Extract(protocol, body)
	if err != nil {
		return ContentModerationInput{}, false, nil, err
	}
	var parts []string
	for _, segment := range document.Segments {
		if !isModerationDirectUser(protocol, segment.Role, segment.Source, segment.Current) {
			continue
		}
		if text := moderationUserText(segment.Text); text != "" {
			parts = append(parts, text)
		}
	}

	images := make([]string, 0, len(document.Images))
	for _, image := range document.Images {
		if isModerationDirectUser(protocol, image.Role, image.Source, image.Current) {
			images = append(images, image.URL)
		}
	}
	out := ContentModerationInput{
		Text:   normalizeContentModerationText(strings.Join(parts, "\n")),
		Images: normalizeModerationImages(images),
	}
	if applyRuneBudget {
		out.Normalize()
	} else {
		out.Images = normalizeModerationImages(out.Images)
	}
	if document.Incomplete {
		return out, true, auditcontent.SanitizeIncompleteReasons(document.IncompleteReasons), nil
	}
	return out, !out.IsEmpty(), nil, nil
}

func isModerationDirectUser(protocol, role string, source auditcontent.Source, current bool) bool {
	if !current {
		return false
	}
	switch source {
	case auditcontent.SourceMessage, auditcontent.SourceSearchQuery, auditcontent.SourceEmbeddingInput, auditcontent.SourceMediaPrompt:
	default:
		return false
	}
	role = strings.ToLower(strings.TrimSpace(role))
	switch protocol {
	case ContentModerationProtocolOpenAIResponses, ContentModerationProtocolOpenAILive, ContentModerationProtocolGemini:
		return role == "user" || role == ""
	default:
		return role == "user"
	}
}

func moderationUserText(text string) string {
	return strings.TrimSpace(text)
}

func normalizeModerationImages(images []string) []string {
	out := make([]string, 0, len(images))
	seen := make(map[string]struct{}, len(images))
	for _, image := range images {
		image = strings.TrimSpace(image)
		if image == "" {
			continue
		}
		if _, ok := seen[image]; ok {
			continue
		}
		seen[image] = struct{}{}
		out = append(out, image)
	}
	return out
}

func limitContentModerationImages(images []string) []string {
	if len(images) <= maxContentModerationInputImages {
		return images
	}
	slog.Warn("content_moderation.images_truncated",
		"image_count", len(images),
		"kept", maxContentModerationInputImages)
	return images[:maxContentModerationInputImages]
}

func normalizeContentModerationText(text string) string {
	return strings.Join(strings.Fields(strings.TrimSpace(text)), " ")
}
