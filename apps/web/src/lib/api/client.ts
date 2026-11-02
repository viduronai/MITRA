import type {
  Business,
  CallDetail,
  CallFilters,
  CallList,
  CallRating,
  CustomerDetail,
  CustomerList,
  ForgetOut,
  HomeSummary,
  MemoryFact,
  MemoryStatus,
  BusinessCreatedOut,
  BusinessIn,
  CatalogVoice,
  CorrectionOut,
  Employee,
  EmployeeIn,
  EmployeePatch,
  Fact,
  FactCategory,
  Gap,
  KnowledgeSource,
  Locale,
  MeOut,
  OnboardingProgress,
  OtpRequestOut,
  OtpVerifyOut,
  Rate,
  RoleTemplate,
  SourceIn,
  TestCall,
} from "./types";

/** Error from the core API, normalised from `{"error": {code, message}}`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Everything the web app asks of services/core. Two implementations share it:
 * the real HTTP client (http.ts) and an in-memory mock (mock.ts) used while
 * the API is not running (MITRA_API_MOCK=1). Server-side only: `token` is the
 * session JWT read from the httpOnly cookie.
 */
export interface MitraApi {
  requestOtp(phone: string): Promise<OtpRequestOut>;
  verifyOtp(requestId: string, code: string): Promise<OtpVerifyOut>;
  me(token: string): Promise<MeOut>;

  createBusiness(token: string, body: BusinessIn, idempotencyKey?: string): Promise<BusinessCreatedOut>;
  currentBusiness(token: string): Promise<Business>;
  updateBusiness(token: string, body: Partial<BusinessIn>): Promise<Business>;

  listEmployees(token: string): Promise<Employee[]>;
  createEmployee(token: string, body: EmployeeIn, idempotencyKey?: string): Promise<Employee>;
  updateEmployee(token: string, id: string, body: EmployeePatch): Promise<Employee>;

  roleTemplates(token: string): Promise<RoleTemplate[]>;
  voices(token: string, language?: Locale): Promise<CatalogVoice[]>;
  rates(token: string): Promise<Rate[]>;

  addSource(token: string, body: SourceIn): Promise<KnowledgeSource>;
  listSources(token: string): Promise<KnowledgeSource[]>;
  listFacts(token: string): Promise<Fact[]>;
  addFact(token: string, body: { category: FactCategory; key: string; value: string }): Promise<Fact>;
  updateFact(token: string, id: string, body: { value?: string; status?: "confirmed" }): Promise<Fact>;
  deleteFact(token: string, id: string): Promise<void>;
  listGaps(token: string): Promise<Gap[]>;

  startTestCall(token: string, employeeId: string): Promise<TestCall>;
  getTestCall(token: string, id: string): Promise<TestCall>;
  addCorrection(token: string, testCallId: string, text: string): Promise<CorrectionOut>;

  listCalls(token: string, filters?: CallFilters): Promise<CallList>;
  getCall(token: string, id: string): Promise<CallDetail>;
  rateCall(token: string, id: string, rating: CallRating, reason?: string): Promise<void>;
  /** CSV text (UTF-8 with BOM) for the same filters as the list. */
  exportCalls(token: string, filters?: CallFilters): Promise<string>;
  homeSummary(token: string): Promise<HomeSummary>;

  listCustomers(token: string, q?: string): Promise<CustomerList>;
  getCustomer(token: string, id: string): Promise<CustomerDetail>;
  updateMemory(
    token: string,
    customerId: string,
    factId: string,
    body: { value?: string; status?: MemoryStatus },
  ): Promise<MemoryFact>;
  deleteMemory(token: string, customerId: string, factId: string): Promise<void>;
  /** DPDP erasure: the customer, their calls, transcripts and memory. */
  forgetCustomer(token: string, customerId: string): Promise<ForgetOut>;

  /** go_live stays false in Step 2 (a number and wallet come later), so 83% is "set up". */
  progress(token: string): Promise<OnboardingProgress>;
}
