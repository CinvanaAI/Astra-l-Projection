#include "AgentEmbodimentCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "Misc/CommandLine.h"
#include "Misc/App.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/Crc.h"
#include "RenderingThread.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogAgentEmbodiment, Log, All);

namespace Embodiment
{
    // Prevent same-process PIE worlds sharing a queue; the system mutex covers other processes.
    TSet<FString> OwnedQueues;

    bool SafeId(const FString& Id)
    {
        if (Id.IsEmpty() || Id.Len() > 64) return false;
        for (const TCHAR C : Id)
            if (!((C >= 'a' && C <= 'z') || (C >= 'A' && C <= 'Z') ||
                  (C >= '0' && C <= '9') || C == '_' || C == '-')) return false;
        return true;
    }

    bool ValidText(const FString& Text)
    {
        if (Text.Len() < 1 || Text.Len() > 500 || Text.TrimStartAndEnd().IsEmpty()) return false;
        for (int32 Index = 0; Index < Text.Len(); ++Index)
        {
            const uint32 Unit = static_cast<uint32>(Text[Index]);
            if ((Unit < 32 && Unit != '\n' && Unit != '\t') || Unit == 127) return false;
            if (Unit >= 0xD800 && Unit <= 0xDBFF)
            {
                if (++Index >= Text.Len()) return false;
                const uint32 Next = static_cast<uint32>(Text[Index]);
                if (Next < 0xDC00 || Next > 0xDFFF) return false;
            }
            else if (Unit >= 0xDC00 && Unit <= 0xDFFF) return false;
        }
        return true;
    }

    bool ReadNumber(const TSharedPtr<FJsonObject>& J, const TCHAR* Key, double Min, double Max,
                    float& Result, bool bRequired = true)
    {
        double Value = 0;
        if (!J->TryGetNumberField(Key, Value)) return !bRequired && !J->HasField(Key);
        if (!FMath::IsFinite(Value) || Value < Min || Value > Max) return false;
        Result = static_cast<float>(Value);
        return true;
    }

    TSharedRef<FJsonObject> VectorJson(const FVector& V)
    {
        const auto Json = MakeShared<FJsonObject>();
        Json->SetNumberField(TEXT("x"), V.X);
        Json->SetNumberField(TEXT("y"), V.Y);
        Json->SetNumberField(TEXT("z"), V.Z);
        return Json;
    }
}

AAgentEmbodimentCharacter::AAgentEmbodimentCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(34, 88);
    GetCharacterMovement()->MaxWalkSpeed = 150;
    GetCharacterMovement()->MaxAcceleration = 800;
    GetCharacterMovement()->BrakingDecelerationWalking = 1200;
    GetCharacterMovement()->bRunPhysicsWithNoController = true;
    GetCharacterMovement()->bOrientRotationToMovement = false;
    bUseControllerRotationYaw = false;
    AutoPossessPlayer = EAutoReceiveInput::Disabled;
    AutoPossessAI = EAutoPossessAI::Disabled;

    EyeCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("EyeCamera"));
    EyeCamera->SetupAttachment(GetCapsuleComponent());
    EyeCamera->SetRelativeLocation(FVector(0, 0, 64));
    EyeCamera->FieldOfView = 80;
    EyeCamera->bUsePawnControlRotation = false;
    EyeCapture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("EyeCapture"));
    EyeCapture->SetupAttachment(EyeCamera);
    EyeCapture->bCaptureEveryFrame = false;
    EyeCapture->bCaptureOnMovement = false;
    EyeCapture->bAlwaysPersistRenderingState = true;
    EyeCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
    EyeCapture->PostProcessSettings.bOverride_AutoExposureMethod = true;
    EyeCapture->PostProcessSettings.AutoExposureMethod = EAutoExposureMethod::AEM_Manual;
    EyeCapture->PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
    EyeCapture->PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;

    DiagnosticProxy = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DiagnosticProxy"));
    DiagnosticProxy->SetupAttachment(GetCapsuleComponent());
    DiagnosticProxy->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    if (Cylinder.Succeeded()) DiagnosticProxy->SetStaticMesh(Cylinder.Object);
    DiagnosticProxy->SetRelativeScale3D(FVector(.55, .55, 1.6));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void AAgentEmbodimentCharacter::BeginPlay()
{
    Super::BeginPlay();
    QueueRoot = QueueDirectory.IsEmpty() ? FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AgentEmbodiment")) : QueueDirectory;
    FParse::Value(FCommandLine::Get(), TEXT("AgentQueue="), QueueRoot);
    QueueRoot = FPaths::ConvertRelativePathToFull(QueueRoot);
    FPaths::NormalizeDirectoryName(QueueRoot);
    FPaths::CollapseRelativeDirectories(QueueRoot);
    const FString QueueKey = QueueRoot.ToLower();
    if (Embodiment::OwnedQueues.Contains(QueueKey))
    {
        UE_LOG(LogAgentEmbodiment, Error, TEXT("Queue already owned in this process; use one agent and one Play instance."));
        return;
    }
    QueueLock = MakeUnique<FSystemWideCriticalSection>(FString::Printf(TEXT("AgentEmbodiment_%08x"), FCrc::StrCrc32(*QueueKey)));
    if (!QueueLock->IsValid())
    {
        QueueLock.Reset();
        UE_LOG(LogAgentEmbodiment, Error, TEXT("Queue already owned by another process."));
        return;
    }
    for (const TCHAR* Subdirectory : { TEXT("inbox"), TEXT("processed"), TEXT("outbox"), TEXT("captures"), TEXT("chat-events") })
        if (!IFileManager::Get().MakeDirectory(*FPaths::Combine(QueueRoot, Subdirectory), true))
        {
            QueueLock.Reset();
            UE_LOG(LogAgentEmbodiment, Error, TEXT("Cannot create queue directory: %s"), *QueueRoot);
            return;
        }
    Embodiment::OwnedQueues.Add(QueueKey);
    SessionId = FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower);
    StartedAtUtc = FDateTime::UtcNow().ToIso8601();
    ViewRotation = EyeCamera->GetComponentRotation();
    DiagnosticProxy->SetVisibility(bShowDiagnosticProxy && !GetMesh()->GetSkeletalMeshAsset());
    EyeCapture->HideComponent(DiagnosticProxy);
    EyeCapture->HideComponent(GetMesh());
    CaptureTarget = NewObject<UTextureRenderTarget2D>(this);
    CaptureTarget->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;
    CaptureTarget->InitAutoFormat(640, 360);
    CaptureTarget->UpdateResourceImmediate(true);
    EyeCapture->TextureTarget = CaptureTarget;
    bRunning = true;
    ApplyViewRotation();
    WriteRuntime();
    UE_LOG(LogAgentEmbodiment, Display, TEXT("Embodiment session %s ready at %s"), *SessionId, *QueueRoot);
}

void AAgentEmbodimentCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    if (bRunning)
    {
        LocalEmergencyStop();
        bRunning = false;
        WriteRuntime();
        Embodiment::OwnedQueues.Remove(QueueRoot.ToLower());
    }
    QueueLock.Reset();
    Super::EndPlay(Reason);
}

AAgentEmbodimentCharacter* AAgentEmbodimentCharacter::FindAgent(UWorld* World)
{
    if (!World) return nullptr;
    for (TActorIterator<AAgentEmbodimentCharacter> It(World); It; ++It)
        if (It->IsQueueRunning()) return *It;
    return nullptr;
}

void AAgentEmbodimentCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bRunning) return;
    const double Now = FPlatformTime::Seconds();
    if (Now >= PollAt) { PollAt = Now + .05; PollQueue(); }
    if (Now >= HeartbeatAt) { HeartbeatAt = Now + 1; WriteRuntime(); }
    if (!bMoving) return;
    if (Now >= MoveDeadline) { FinishMove(TEXT("completed")); return; }
    if (FVector::DotProduct(GetActorLocation() - ProgressPosition, MoveDirection) >= 1)
    {
        ProgressPosition = GetActorLocation();
        LastProgressAt = Now;
    }
    // A bounded command reports stopped progress; this starter makes no navigation claim.
    if (Now - LastProgressAt > .4) { FinishMove(TEXT("blocked"), TEXT("no_forward_progress")); return; }
    AddMovementInput(MoveDirection, FMath::Min(1.f, FVector2D(ActiveMove.Forward, ActiveMove.Right).Size()), true);
}

void AAgentEmbodimentCharacter::ApplyViewRotation()
{
    SetActorRotation(FRotator(0, ViewRotation.Yaw, 0));
    EyeCamera->SetWorldRotation(ViewRotation);
}

void AAgentEmbodimentCharacter::PollQueue()
{
    TArray<FString> Files;
    IFileManager::Get().FindFiles(Files, *FPaths::Combine(QueueRoot, TEXT("inbox/*.json")), true, false);
    Files.Sort();
    for (int32 Index = 0; Index < FMath::Min(Files.Num(), 16); ++Index)
    {
        const FString Id = FPaths::GetBaseFilename(Files[Index]);
        if (!Embodiment::SafeId(Id)) continue;
        const FString InputPath = FPaths::Combine(QueueRoot, TEXT("inbox"), Files[Index]);
        const FString OutputPath = FPaths::Combine(QueueRoot, TEXT("outbox"), Files[Index]);
        FString ClaimedName = Files[Index];
        const bool bPreviouslyClaimed = IFileManager::Get().FileExists(*FPaths::Combine(QueueRoot, TEXT("processed"), ClaimedName));
        if (bPreviouslyClaimed)
            ClaimedName = Id + TEXT("-duplicate-") + FGuid::NewGuid().ToString(EGuidFormats::Digits) + TEXT(".json");
        const FString ClaimedPath = FPaths::Combine(QueueRoot, TEXT("processed"), ClaimedName);
        if (!IFileManager::Get().Move(*ClaimedPath, *InputPath, false, false, false, true)) continue;
        if (bPreviouslyClaimed || IFileManager::Get().FileExists(*OutputPath) || (bMoving && ActiveMove.Id == Id)) continue;
        FCommand Command;
        Command.Id = Id;
        FString Text, Error;
        TSharedPtr<FJsonObject> Json;
        const int64 Size = IFileManager::Get().FileSize(*ClaimedPath);
        if (Size <= 0 || Size > 65536 || !FFileHelper::LoadFileToString(Text, *ClaimedPath) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) || !Json.IsValid())
            Error = TEXT("invalid_json_or_size");
        else ParseCommand(Json, Id, Command, Error);
        if (!Error.IsEmpty()) { Command.bCapture = false; WriteReply(Command, TEXT("rejected"), Error); }
        else ExecuteCommand(Command);
    }
}

bool AAgentEmbodimentCharacter::ParseCommand(const TSharedPtr<FJsonObject>& Json, const FString& Id,
                                            FCommand& Command, FString& Error) const
{
    FString RequestedId, RequestedSession, DeadlineText;
    double Version = 0;
    Json->TryGetStringField(TEXT("action"), Command.Action);
    if (!Json->TryGetNumberField(TEXT("schema_version"), Version) || Version != 1 ||
        !Json->TryGetStringField(TEXT("id"), RequestedId) || RequestedId != Id ||
        !Json->TryGetStringField(TEXT("session_id"), RequestedSession) || RequestedSession != SessionId)
    { Error = TEXT("invalid_identity_schema_or_session"); return false; }
    FDateTime Deadline;
    if (!Json->TryGetStringField(TEXT("deadline_utc"), DeadlineText) ||
        !FDateTime::ParseIso8601(*DeadlineText, Deadline) || Deadline <= FDateTime::UtcNow())
    { Error = TEXT("invalid_or_expired_deadline"); return false; }
    if (Command.Action != TEXT("observe") && Command.Action != TEXT("stop"))
    {
        double Revision = 0;
        if (!Json->TryGetNumberField(TEXT("expected_stop_revision"), Revision) || !FMath::IsFinite(Revision) ||
            Revision < 0 || Revision > 9007199254740991. || FMath::FloorToDouble(Revision) != Revision ||
            static_cast<int64>(Revision) != StopRevision)
        { Error = TEXT("stop_revision_changed_or_invalid"); return false; }
    }
    Command.bCapture = true;
    if (Json->HasField(TEXT("capture")) && !Json->TryGetBoolField(TEXT("capture"), Command.bCapture))
    { Error = TEXT("invalid_capture_flag"); return false; }
    if (Command.Action == TEXT("move"))
    {
        if (!Embodiment::ReadNumber(Json, TEXT("forward"), -1, 1, Command.Forward) ||
            !Embodiment::ReadNumber(Json, TEXT("right"), -1, 1, Command.Right) ||
            !Embodiment::ReadNumber(Json, TEXT("seconds"), .05, 2, Command.Seconds) ||
            !Embodiment::ReadNumber(Json, TEXT("speed_cm_s"), 1, 300, Command.Speed, false) ||
            FVector2D(Command.Forward, Command.Right).IsNearlyZero()) Error = TEXT("invalid_move_bounds");
    }
    else if (Command.Action == TEXT("look"))
    {
        if (!Embodiment::ReadNumber(Json, TEXT("yaw_delta_deg"), -90, 90, Command.YawDelta) ||
            !Embodiment::ReadNumber(Json, TEXT("pitch_delta_deg"), -60, 60, Command.PitchDelta)) Error = TEXT("invalid_look_bounds");
    }
    else if (Command.Action == TEXT("say"))
    {
        if (!Json->TryGetStringField(TEXT("text"), Command.Text) || !Embodiment::ValidText(Command.Text)) Error = TEXT("invalid_say_text");
        if (Json->HasField(TEXT("reply_to_event_id")))
        {
            double ReplyId = 0;
            if (!Json->TryGetNumberField(TEXT("reply_to_event_id"), ReplyId) || !FMath::IsFinite(ReplyId) ||
                ReplyId < 1 || ReplyId > 9007199254740991. || FMath::FloorToDouble(ReplyId) != ReplyId ||
                !HumanEventIds.Contains(static_cast<int64>(ReplyId))) Error = TEXT("invalid_reply_to_event_id");
            else Command.ReplyToEventId = static_cast<int64>(ReplyId);
        }
    }
    else if (Command.Action != TEXT("observe") && Command.Action != TEXT("stop")) Error = TEXT("unsupported_action");
    return Error.IsEmpty();
}

void AAgentEmbodimentCharacter::ExecuteCommand(const FCommand& Command)
{
    if (Command.Action == TEXT("move"))
    {
        if (bMoving) { WriteReply(Command, TEXT("rejected"), TEXT("busy")); return; }
        ActiveMove = Command;
        MoveDirection = (GetActorForwardVector() * Command.Forward + GetActorRightVector() * Command.Right).GetSafeNormal();
        MoveDeadline = FPlatformTime::Seconds() + Command.Seconds;
        LastProgressAt = FPlatformTime::Seconds();
        ProgressPosition = GetActorLocation();
        GetCharacterMovement()->MaxWalkSpeed = Command.Speed;
        bMoving = true;
        return;
    }
    if (Command.Action == TEXT("stop")) LocalEmergencyStop();
    else if (Command.Action == TEXT("look"))
    {
        if (bMoving) { WriteReply(Command, TEXT("rejected"), TEXT("busy")); return; }
        ViewRotation.Yaw = FRotator::NormalizeAxis(ViewRotation.Yaw + Command.YawDelta);
        ViewRotation.Pitch = FMath::Clamp(ViewRotation.Pitch + Command.PitchDelta, -80.0, 80.0);
        ApplyViewRotation();
    }
    else if (Command.Action == TEXT("say"))
    {
        FString Error;
        if (!RecordSpeech(TEXT("agent"), Command.Text, Error, Command.ReplyToEventId))
        { WriteReply(Command, TEXT("rejected"), Error); return; }
    }
    WriteReply(Command, TEXT("completed"));
}

void AAgentEmbodimentCharacter::StopMotor()
{
    ConsumeMovementInputVector();
    GetCharacterMovement()->StopMovementImmediately();
}

void AAgentEmbodimentCharacter::FinishMove(const FString& Status, const FString& Error)
{
    FCommand Completed = ActiveMove;
    if (Status == TEXT("interrupted")) Completed.bCapture = false;
    bMoving = false;
    ActiveMove = FCommand();
    StopMotor();
    WriteReply(Completed, Status, Error);
}

void AAgentEmbodimentCharacter::LocalEmergencyStop()
{
    ++StopRevision;
    if (bMoving) FinishMove(TEXT("interrupted"), TEXT("stop_requested"));
    StopMotor();
    if (bRunning) WriteRuntime();
}

bool AAgentEmbodimentCharacter::ReceiveHumanMessage(const FString& Text, FString& Error)
{
    if (!bRunning) { Error = TEXT("agent_queue_unavailable"); return false; }
    return RecordSpeech(TEXT("human"), Text, Error);
}

bool AAgentEmbodimentCharacter::RecordSpeech(const FString& Speaker, const FString& Text, FString& Error, int64 ReplyToEventId)
{
    if (!Embodiment::ValidText(Text)) { Error = TEXT("Use 1-500 characters, with no control characters."); return false; }
    const auto Event = MakeShared<FJsonObject>();
    const int64 NextId = ChatEventId + 1;
    Event->SetNumberField(TEXT("schema_version"), 1);
    Event->SetStringField(TEXT("session_id"), SessionId);
    Event->SetNumberField(TEXT("event_id"), NextId);
    Event->SetStringField(TEXT("speaker"), Speaker);
    Event->SetStringField(TEXT("speaker_actor"), Speaker == TEXT("agent") ? GetName() : TEXT("local_human"));
    Event->SetStringField(TEXT("text"), Text);
    Event->SetStringField(TEXT("occurred_at_utc"), FDateTime::UtcNow().ToIso8601());
    Event->SetNumberField(TEXT("world_time_seconds"), GetWorld()->GetTimeSeconds());
    Event->SetStringField(TEXT("source"), TEXT("local_world_text_event"));
    Event->SetStringField(TEXT("modality"), TEXT("text_only_no_audio_or_gesture"));
    if (ReplyToEventId > 0) Event->SetNumberField(TEXT("reply_to_event_id"), ReplyToEventId);
    const FString Path = FPaths::Combine(QueueRoot, TEXT("chat-events"), SessionId + FString::Printf(TEXT("-%020lld.json"), NextId));
    if (!AtomicJson(Path, Event, false)) { Error = TEXT("chat_event_persist_failed"); return false; }
    ChatEventId = NextId;
    if (Speaker == TEXT("human")) { LatestHumanMessage = Event; HumanEventIds.Add(NextId); }
    Transcript.Add((Speaker == TEXT("human") ? TEXT("You: ") : TEXT("Agent: ")) + Text);
    if (Transcript.Num() > 12) Transcript.RemoveAt(0);
    return true;
}

TSharedRef<FJsonObject> AAgentEmbodimentCharacter::MakeState()
{
    const auto State = MakeShared<FJsonObject>();
    State->SetNumberField(TEXT("observation_id"), ++ObservationId);
    State->SetStringField(TEXT("captured_at_utc"), FDateTime::UtcNow().ToIso8601());
    State->SetObjectField(TEXT("position_cm"), Embodiment::VectorJson(GetActorLocation()));
    State->SetObjectField(TEXT("velocity_cm_s"), Embodiment::VectorJson(GetVelocity()));
    const auto Rotation = MakeShared<FJsonObject>();
    Rotation->SetNumberField(TEXT("pitch"), ViewRotation.Pitch);
    Rotation->SetNumberField(TEXT("yaw"), ViewRotation.Yaw);
    Rotation->SetNumberField(TEXT("roll"), ViewRotation.Roll);
    State->SetObjectField(TEXT("view_rotation_deg"), Rotation);
    State->SetBoolField(TEXT("is_moving"), bMoving);
    State->SetBoolField(TEXT("grounded"), GetCharacterMovement()->IsMovingOnGround());
    State->SetNumberField(TEXT("stop_revision"), StopRevision);
    State->SetStringField(TEXT("chat_events_path"), FPaths::Combine(QueueRoot, TEXT("chat-events")));
    State->SetNumberField(TEXT("latest_chat_event_id"), ChatEventId);
    if (LatestHumanMessage.IsValid()) State->SetObjectField(TEXT("latest_human_message"), LatestHumanMessage.ToSharedRef());
    return State;
}

bool AAgentEmbodimentCharacter::CaptureEye(const FString& Id, FString& ImagePath, FString& Error)
{
    if (!CaptureTarget || !GetWorld() || !GetWorld()->Scene || !FApp::CanEverRender())
    { Error = TEXT("renderer_unavailable"); return false; }
    EyeCapture->SetWorldLocationAndRotation(EyeCamera->GetComponentLocation(), EyeCamera->GetComponentRotation());
    EyeCapture->FOVAngle = EyeCamera->FieldOfView;
    EyeCapture->CaptureScene();
    FlushRenderingCommands();
    FImage CapturedImage;
    TArray64<uint8> Png;
    if (!FImageUtils::GetRenderTargetImage(CaptureTarget, CapturedImage) ||
        !FImageUtils::CompressImage(Png, TEXT("PNG"), CapturedImage) || Png.Num() == 0)
    { Error = TEXT("png_encoding_failed"); return false; }
    ImagePath = FPaths::Combine(QueueRoot, TEXT("captures"), Id + TEXT(".png"));
    const FString Temporary = ImagePath + TEXT(".tmp");
    if (!FFileHelper::SaveArrayToFile(Png, *Temporary) || !IFileManager::Get().Move(*ImagePath, *Temporary, true, false, false, true))
    { ImagePath.Empty(); Error = TEXT("png_write_failed"); return false; }
    return true;
}

bool AAgentEmbodimentCharacter::AtomicJson(const FString& Filename, const TSharedRef<FJsonObject>& Json, bool bReplace) const
{
    FString Text;
    if (!FJsonSerializer::Serialize(Json, TJsonWriterFactory<>::Create(&Text))) return false;
    const FString Temporary = Filename + TEXT(".tmp");
    return FFileHelper::SaveStringToFile(Text, *Temporary, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) &&
        IFileManager::Get().Move(*Filename, *Temporary, bReplace, false, false, true);
}

void AAgentEmbodimentCharacter::WriteReply(const FCommand& Command, const FString& Status, const FString& Error)
{
    if (Command.Id.IsEmpty()) return;
    const auto Reply = MakeShared<FJsonObject>();
    Reply->SetNumberField(TEXT("schema_version"), 1);
    Reply->SetStringField(TEXT("session_id"), SessionId);
    Reply->SetStringField(TEXT("id"), Command.Id);
    Reply->SetStringField(TEXT("action"), Command.Action);
    Reply->SetBoolField(TEXT("ok"), Status == TEXT("completed"));
    Reply->SetStringField(TEXT("status"), Status);
    if (!Error.IsEmpty()) Reply->SetStringField(TEXT("error"), Error);
    const auto State = MakeState();
    Reply->SetObjectField(TEXT("state"), State);
    FString ImagePath, CaptureError;
    if (Command.bCapture && CaptureEye(Command.Id, ImagePath, CaptureError))
    {
        const auto Capture = MakeShared<FJsonObject>();
        Capture->SetStringField(TEXT("path"), ImagePath);
        Capture->SetNumberField(TEXT("width"), 640);
        Capture->SetNumberField(TEXT("height"), 360);
        Capture->SetStringField(TEXT("view"), TEXT("first_person"));
        Capture->SetNumberField(TEXT("observation_id"), ObservationId);
        Reply->SetObjectField(TEXT("capture"), Capture);
    }
    else if (Command.bCapture) Reply->SetStringField(TEXT("capture_error"), CaptureError);
    if (!AtomicJson(FPaths::Combine(QueueRoot, TEXT("outbox"), Command.Id + TEXT(".json")), Reply, false))
        UE_LOG(LogAgentEmbodiment, Error, TEXT("Could not write command reply: %s"), *Command.Id);
}

void AAgentEmbodimentCharacter::WriteRuntime()
{
    const auto Json = MakeShared<FJsonObject>();
    Json->SetNumberField(TEXT("schema_version"), 1);
    Json->SetStringField(TEXT("session_id"), SessionId);
    Json->SetBoolField(TEXT("running"), bRunning);
    Json->SetStringField(TEXT("queue_root"), QueueRoot);
    Json->SetStringField(TEXT("started_at_utc"), StartedAtUtc);
    Json->SetStringField(TEXT("updated_at_utc"), FDateTime::UtcNow().ToIso8601());
    Json->SetNumberField(TEXT("stop_revision"), StopRevision);
    Json->SetStringField(TEXT("pawn"), GetName());
    Json->SetStringField(TEXT("chat_events_path"), FPaths::Combine(QueueRoot, TEXT("chat-events")));
    Json->SetStringField(TEXT("control_owner"), TEXT("conversational_agent_queue"));
    TArray<TSharedPtr<FJsonValue>> Actions;
    for (const TCHAR* Action : { TEXT("observe"), TEXT("move"), TEXT("look"), TEXT("stop"), TEXT("say") })
        Actions.Add(MakeShared<FJsonValueString>(Action));
    Json->SetArrayField(TEXT("supported_actions"), Actions);
    if (!AtomicJson(FPaths::Combine(QueueRoot, TEXT("runtime.json")), Json))
        UE_LOG(LogAgentEmbodiment, Error, TEXT("Could not write runtime heartbeat."));
}
