#include "AgentEmbodimentGameMode.h"

#include "AgentEmbodimentCharacter.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

AAgentEmbodimentGameMode::AAgentEmbodimentGameMode()
{
    DefaultPawnClass = AEmbodimentHumanCharacter::StaticClass();
    PlayerControllerClass = AEmbodimentPlayerController::StaticClass();
}

AEmbodimentHumanCharacter::AEmbodimentHumanCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(34, 88);
    GetCharacterMovement()->MaxWalkSpeed = 220;
    GetCharacterMovement()->bOrientRotationToMovement = false;
    bUseControllerRotationYaw = true;
    HumanCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("HumanCamera"));
    HumanCamera->SetupAttachment(GetCapsuleComponent());
    HumanCamera->SetRelativeLocation(FVector(0, 0, 64));
    HumanCamera->bUsePawnControlRotation = true;
    HumanCamera->FieldOfView = 80;
}

void AEmbodimentHumanCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    AEmbodimentPlayerController* PC = Cast<AEmbodimentPlayerController>(Controller);
    if (!PC || !PC->IsLocalController() || PC->IsChatOpen()) return;
    float MouseX = 0, MouseY = 0;
    PC->GetInputMouseDelta(MouseX, MouseY);
    FRotator Rotation = PC->GetControlRotation();
    Rotation.Yaw += MouseX * .15;
    Rotation.Pitch = FMath::Clamp(FRotator::NormalizeAxis(Rotation.Pitch - MouseY * .15), -80.0, 80.0);
    PC->SetControlRotation(Rotation);
    const FRotator Yaw(0, Rotation.Yaw, 0);
    const float Forward = float(PC->IsInputKeyDown(EKeys::W)) - float(PC->IsInputKeyDown(EKeys::S));
    const float Right = float(PC->IsInputKeyDown(EKeys::D)) - float(PC->IsInputKeyDown(EKeys::A));
    AddMovementInput(Yaw.Vector(), Forward);
    AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Right);
}

void AEmbodimentPlayerController::BeginPlay()
{
    Super::BeginPlay();
    if (!IsLocalController() || !GEngine || !GEngine->GameViewport || !FSlateApplication::IsInitialized()) return;
    ChatPanel = SNew(SOverlay)
        + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Bottom).Padding(16)
        [
            SNew(SBox).WidthOverride(440).HeightOverride(300)
            [
                SNew(SBorder).Padding(12).BorderBackgroundColor(FLinearColor(.025f, .035f, .05f, .92f))
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                    [SNew(STextBlock).Text(FText::FromString(TEXT("EMBODIMENT  |  T chat  |  F10 stop agent")))]
                    + SVerticalBox::Slot().FillHeight(1)
                    [
                        SNew(SScrollBox)
                        + SScrollBox::Slot()
                        [SAssignNew(ChatHistory, STextBlock).AutoWrapText(true)]
                    ]
                    + SVerticalBox::Slot().AutoHeight().Padding(0, 8, 0, 0)
                    [
                        SAssignNew(ChatInput, SEditableTextBox)
                        .HintText(FText::FromString(TEXT("Press T to chat. Enter sends. Esc cancels.")))
                        .IsReadOnly(true)
                        .OnTextCommitted(FOnTextCommitted::CreateUObject(this, &AEmbodimentPlayerController::SubmitChat))
                        .OnKeyDownHandler(FOnKeyDown::CreateUObject(this, &AEmbodimentPlayerController::ChatKeyDown))
                    ]
                ]
            ]
        ];
    GEngine->GameViewport->AddViewportWidgetContent(ChatPanel.ToSharedRef(), 10);
    bShowMouseCursor = false;
    SetInputMode(FInputModeGameOnly());
    bReady = true;
}

void AEmbodimentPlayerController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bReady) return;
    AAgentEmbodimentCharacter* Agent = AAgentEmbodimentCharacter::FindAgent(GetWorld());
    if (WasInputKeyJustPressed(EKeys::F10) && Agent) Agent->LocalEmergencyStop();
    if (!bChatOpen && WasInputKeyJustPressed(EKeys::T)) OpenChat();
    const FString Transcript = Agent ? Agent->GetChatTranscript() : TEXT("Place one AgentEmbodimentCharacter in this map and press Play.");
    if (Transcript != LastTranscript)
    {
        LastTranscript = Transcript;
        ChatHistory->SetText(FText::FromString(Transcript.IsEmpty() ? TEXT("Ready. Chat appears here. A bridge is needed for agent replies.") : Transcript));
    }
}

void AEmbodimentPlayerController::OpenChat()
{
    if (!ChatInput.IsValid()) return;
    bChatOpen = true;
    if (ACharacter* Human = Cast<ACharacter>(GetPawn())) Human->GetCharacterMovement()->StopMovementImmediately();
    FlushPressedKeys();
    ChatInput->SetIsReadOnly(false);
    bShowMouseCursor = true;
    SetInputMode(FInputModeGameAndUI().SetWidgetToFocus(ChatInput.ToSharedRef()).SetHideCursorDuringCapture(false));
    FSlateApplication::Get().SetKeyboardFocus(ChatInput, EFocusCause::SetDirectly);
}

void AEmbodimentPlayerController::CloseChat()
{
    bChatOpen = false;
    ChatInput->SetIsReadOnly(true);
    ChatInput->SetError(FText::GetEmpty());
    FlushPressedKeys();
    bShowMouseCursor = false;
    SetInputMode(FInputModeGameOnly());
    FSlateApplication::Get().SetAllUserFocusToGameViewport(EFocusCause::SetDirectly);
}

void AEmbodimentPlayerController::SubmitChat(const FText& Text, ETextCommit::Type Type)
{
    if (!bChatOpen || Type != ETextCommit::OnEnter) return;
    AAgentEmbodimentCharacter* Agent = AAgentEmbodimentCharacter::FindAgent(GetWorld());
    FString Error = TEXT("No running agent in this world.");
    if (!Agent || !Agent->ReceiveHumanMessage(Text.ToString(), Error))
    { ChatInput->SetError(FText::FromString(Error)); return; }
    ChatInput->SetText(FText::GetEmpty());
    CloseChat();
}

FReply AEmbodimentPlayerController::ChatKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
    if (Event.GetKey() == EKeys::Escape) { CloseChat(); return FReply::Handled(); }
    if (Event.GetKey() == EKeys::F10)
    {
        if (AAgentEmbodimentCharacter* Agent = AAgentEmbodimentCharacter::FindAgent(GetWorld())) Agent->LocalEmergencyStop();
        return FReply::Handled();
    }
    return FReply::Unhandled();
}

void AEmbodimentPlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
    if (ChatPanel.IsValid() && GEngine && GEngine->GameViewport)
        GEngine->GameViewport->RemoveViewportWidgetContent(ChatPanel.ToSharedRef());
    ChatPanel.Reset();
    ChatInput.Reset();
    ChatHistory.Reset();
    Super::EndPlay(Reason);
}
