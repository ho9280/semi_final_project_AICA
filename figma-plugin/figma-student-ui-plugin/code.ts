// 인사교 학생용 모바일 메인 화면 생성 플러그인
// 이모지 대신 SVG 벡터 도형 아이콘 사용

type FontWeight = "Regular" | "Medium" | "Bold";

type RGBColor = {
  r: number;
  g: number;
  b: number;
};

type FeatureIconType =
  | "calculator"
  | "robot"
  | "bell"
  | "megaphone";

type FeatureCardData = {
  title: string;
  description: string;
  iconType: FeatureIconType;
};

type NavIconType =
  | "home"
  | "bell"
  | "message"
  | "megaphone";

type NavItemData = {
  label: string;
  iconType: NavIconType;
  centerX: number;
  active: boolean;
};

const TEXT_COLOR: RGBColor = {
  r: 0.12,
  g: 0.12,
  b: 0.14,
};

const SUB_TEXT_COLOR: RGBColor = {
  r: 0.43,
  g: 0.45,
  b: 0.5,
};

const PRIMARY_COLOR: RGBColor = {
  r: 0.32,
  g: 0.67,
  b: 0.94,
};

const PRIMARY_DARK_COLOR: RGBColor = {
  r: 0.18,
  g: 0.55,
  b: 0.85,
};

const WHITE: RGBColor = {
  r: 1,
  g: 1,
  b: 1,
};

const ICON_BACKGROUND_COLOR: RGBColor = {
  r: 0.89,
  g: 0.95,
  b: 1,
};

const INACTIVE_NAV_COLOR = "#7A808C";
const ACTIVE_ICON_COLOR = "#2E8CD9";

async function createText(
  text: string,
  fontSize: number,
  fontWeight: FontWeight = "Regular",
  color: RGBColor = TEXT_COLOR
): Promise<TextNode> {
  await figma.loadFontAsync({
    family: "Inter",
    style: fontWeight,
  });

  const node = figma.createText();

  node.fontName = {
    family: "Inter",
    style: fontWeight,
  };

  node.characters = text;
  node.fontSize = fontSize;

  node.fills = [
    {
      type: "SOLID",
      color,
    },
  ];

  return node;
}

function createCard(
  width: number,
  height: number,
  radius = 16
): FrameNode {
  const card = figma.createFrame();

  card.resize(width, height);
  card.cornerRadius = radius;
  card.clipsContent = false;

  card.fills = [
    {
      type: "SOLID",
      color: WHITE,
    },
  ];

  card.effects = [
    {
      type: "DROP_SHADOW",
      color: {
        r: 0,
        g: 0,
        b: 0,
        a: 0.08,
      },
      offset: {
        x: 0,
        y: 4,
      },
      radius: 10,
      spread: 0,
      visible: true,
      blendMode: "NORMAL",
    },
  ];

  return card;
}

function createDivider(width: number): RectangleNode {
  const divider = figma.createRectangle();

  divider.resize(width, 1);

  divider.fills = [
    {
      type: "SOLID",
      color: {
        r: 0.9,
        g: 0.91,
        b: 0.93,
      },
    },
  ];

  return divider;
}

/**
 * SVG 코드를 Figma 벡터 도형으로 변환
 * 플러그인 실행 후에도 Figma에서 크기·색상·선 수정 가능
 */
function createSvgIcon(
  svgBody: string,
  color: string,
  size: number,
  name: string
): FrameNode {
  const svg = `
    <svg
      width="${size}"
      height="${size}"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g
        stroke="${color}"
        stroke-width="1.9"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        ${svgBody}
      </g>
    </svg>
  `;

  const icon = figma.createNodeFromSvg(svg);

  icon.name = name;
  icon.resize(size, size);

  return icon;
}

function createCalculatorIcon(
  color: string,
  size = 24
): FrameNode {
  return createSvgIcon(
    `
      <rect x="5" y="2.5" width="14" height="19" rx="2.5"/>
      <rect x="7.5" y="5" width="9" height="4" rx="1"/>
      <path d="M8 12.5H9"/>
      <path d="M11.5 12.5H12.5"/>
      <path d="M15 12.5H16"/>
      <path d="M8 16H9"/>
      <path d="M11.5 16H12.5"/>
      <path d="M15 16H16"/>
      <path d="M8 19.2H9"/>
      <path d="M11.5 19.2H12.5"/>
      <path d="M15 19.2H16"/>
    `,
    color,
    size,
    "아이콘_계산기"
  );
}

function createRobotIcon(
  color: string,
  size = 24
): FrameNode {
  return createSvgIcon(
    `
      <path d="M12 2.5V5"/>
      <circle cx="12" cy="2.5" r="1"/>
      <rect x="4.5" y="6" width="15" height="13" rx="3"/>
      <path d="M4.5 11H2.5V15H4.5"/>
      <path d="M19.5 11H21.5V15H19.5"/>
      <circle cx="9" cy="11.5" r="1"/>
      <circle cx="15" cy="11.5" r="1"/>
      <path d="M9 15.5C10.7 16.8 13.3 16.8 15 15.5"/>
      <path d="M8 19V21"/>
      <path d="M16 19V21"/>
    `,
    color,
    size,
    "아이콘_로봇"
  );
}

function createBellIcon(
  color: string,
  size = 24
): FrameNode {
  return createSvgIcon(
    `
      <path d="M18 8.5C18 5.2 15.3 3 12 3C8.7 3 6 5.2 6 8.5V12.5L4 16H20L18 12.5V8.5Z"/>
      <path d="M9.5 19C10 20.2 10.8 21 12 21C13.2 21 14 20.2 14.5 19"/>
    `,
    color,
    size,
    "아이콘_공지사항"
  );
}

function createMegaphoneIcon(
  color: string,
  size = 24
): FrameNode {
  return createSvgIcon(
    `
      <path d="M4 10V14"/>
      <path d="M4 10H8L17.5 6V18L8 14H4C2.9 14 2 13.1 2 12C2 10.9 2.9 10 4 10Z"/>
      <path d="M8 14L9.5 20H6.5L5 14"/>
      <path d="M20 9C21.3 10.5 21.3 13.5 20 15"/>
    `,
    color,
    size,
    "아이콘_확성기"
  );
}

function createHomeIcon(
  color: string,
  size = 22
): FrameNode {
  return createSvgIcon(
    `
      <path d="M3 11L12 3L21 11"/>
      <path d="M5.5 9.5V21H18.5V9.5"/>
      <path d="M9.5 21V14H14.5V21"/>
    `,
    color,
    size,
    "아이콘_홈"
  );
}

function createMessageIcon(
  color: string,
  size = 22
): FrameNode {
  return createSvgIcon(
    `
      <path d="M4 4.5H20V16.5H10L5 20V16.5H4V4.5Z"/>
      <path d="M8 9H16"/>
      <path d="M8 12.5H14"/>
    `,
    color,
    size,
    "아이콘_챗봇"
  );
}

function createFeatureIcon(
  iconType: FeatureIconType
): FrameNode {
  switch (iconType) {
    case "calculator":
      return createCalculatorIcon(ACTIVE_ICON_COLOR, 25);

    case "robot":
      return createRobotIcon(ACTIVE_ICON_COLOR, 25);

    case "bell":
      return createBellIcon(ACTIVE_ICON_COLOR, 25);

    case "megaphone":
      return createMegaphoneIcon(ACTIVE_ICON_COLOR, 25);

    default:
      return createMessageIcon(ACTIVE_ICON_COLOR, 25);
  }
}

function createNavigationIcon(
  iconType: NavIconType,
  color: string
): FrameNode {
  switch (iconType) {
    case "home":
      return createHomeIcon(color, 21);

    case "bell":
      return createBellIcon(color, 21);

    case "message":
      return createMessageIcon(color, 21);

    case "megaphone":
      return createMegaphoneIcon(color, 21);

    default:
      return createHomeIcon(color, 21);
  }
}

async function createFeatureCard(
  data: FeatureCardData,
  x: number,
  y: number
): Promise<FrameNode> {
  const card = createCard(169, 124);

  card.name = `기능 카드_${data.title}`;
  card.x = x;
  card.y = y;

  const iconBackground = figma.createEllipse();

  iconBackground.name = `${data.title}_아이콘 배경`;
  iconBackground.resize(42, 42);
  iconBackground.x = 16;
  iconBackground.y = 14;

  iconBackground.fills = [
    {
      type: "SOLID",
      color: ICON_BACKGROUND_COLOR,
    },
  ];

  card.appendChild(iconBackground);

  const icon = createFeatureIcon(data.iconType);

  icon.x = 24.5;
  icon.y = 22.5;

  card.appendChild(icon);

  const title = await createText(
    data.title,
    16,
    "Bold"
  );

  title.x = 16;
  title.y = 62;

  card.appendChild(title);

  const description = await createText(
    data.description,
    11,
    "Regular",
    SUB_TEXT_COLOR
  );

  description.x = 16;
  description.y = 90;

  card.appendChild(description);

  return card;
}

async function createNavigationItem(
  item: NavItemData,
  navigation: FrameNode
): Promise<void> {
  const iconColor = item.active
    ? ACTIVE_ICON_COLOR
    : INACTIVE_NAV_COLOR;

  const navColor: RGBColor = item.active
    ? PRIMARY_DARK_COLOR
    : {
        r: 0.48,
        g: 0.5,
        b: 0.55,
      };

  const icon = createNavigationIcon(
    item.iconType,
    iconColor
  );

  icon.x = item.centerX - 10.5;
  icon.y = 7;

  navigation.appendChild(icon);

  const label = await createText(
    item.label,
    11,
    item.active ? "Bold" : "Regular",
    navColor
  );

  label.textAlignHorizontal = "CENTER";
  label.resize(52, 16);
  label.x = item.centerX - 26;
  label.y = 35;

  navigation.appendChild(label);
}

async function main(): Promise<void> {
  const screen = figma.createFrame();

  screen.name = "STU-001_학생 메인";
  screen.resize(390, 844);
  screen.clipsContent = true;

  screen.fills = [
    {
      type: "SOLID",
      color: {
        r: 0.97,
        g: 0.98,
        b: 0.99,
      },
    },
  ];

  // 상단 환영 영역
  const header = figma.createFrame();

  header.name = "환영 영역";
  header.resize(390, 154);
  header.x = 0;
  header.y = 0;
  header.clipsContent = true;

  header.fills = [
    {
      type: "SOLID",
      color: PRIMARY_COLOR,
    },
  ];

  const greeting = await createText(
    "안녕하세요, OOO님",
    25,
    "Bold",
    WHITE
  );

  greeting.x = 20;
  greeting.y = 42;

  header.appendChild(greeting);

  const greetingSub = await createText(
    "오늘도 인공지능사관학교에서 좋은 하루 보내세요",
    13,
    "Regular",
    {
      r: 0.92,
      g: 0.96,
      b: 1,
    }
  );

  greetingSub.x = 20;
  greetingSub.y = 87;

  header.appendChild(greetingSub);
  screen.appendChild(header);

  // 오늘의 식단
  const mealTitle = await createText(
    "오늘의 식단",
    19,
    "Bold"
  );

  mealTitle.x = 20;
  mealTitle.y = 174;

  screen.appendChild(mealTitle);

  const mealCard = createCard(350, 116);

  mealCard.name = "오늘의 식단 카드";
  mealCard.x = 20;
  mealCard.y = 206;

  const mealType = await createText(
    "KT 중식",
    15,
    "Medium",
    PRIMARY_DARK_COLOR
  );

  mealType.x = 18;
  mealType.y = 16;

  mealCard.appendChild(mealType);

  const mealMenu = await createText(
    "제육볶음 · 계란찜 · 김치",
    17,
    "Bold"
  );

  mealMenu.x = 18;
  mealMenu.y = 46;

  mealCard.appendChild(mealMenu);

  const mealNotice = await createText(
    "식단 정보는 Mock 데이터입니다",
    12,
    "Regular",
    SUB_TEXT_COLOR
  );

  mealNotice.x = 18;
  mealNotice.y = 79;

  mealCard.appendChild(mealNotice);
  screen.appendChild(mealCard);

  // 주요 기능
  const featureTitle = await createText(
    "주요 기능",
    19,
    "Bold"
  );

  featureTitle.x = 20;
  featureTitle.y = 346;

  screen.appendChild(featureTitle);

  const featureData: FeatureCardData[] = [
    {
      title: "출결 계산",
      description: "출석률과 지원 기준 확인",
      iconType: "calculator",
    },
    {
      title: "AI 챗봇",
      description: "학습·생활 관련 질문",
      iconType: "robot",
    },
    {
      title: "공지사항",
      description: "공지 제목 검색 및 조회",
      iconType: "bell",
    },
    {
      title: "민원 신청",
      description: "민원 작성과 상태 확인",
      iconType: "megaphone",
    },
  ];

  const featurePositions = [
    {
      x: 20,
      y: 380,
    },
    {
      x: 201,
      y: 380,
    },
    {
      x: 20,
      y: 516,
    },
    {
      x: 201,
      y: 516,
    },
  ];

  for (
    let index = 0;
    index < featureData.length;
    index++
  ) {
    const card = await createFeatureCard(
      featureData[index],
      featurePositions[index].x,
      featurePositions[index].y
    );

    screen.appendChild(card);
  }

  // 최근 공지사항
  const noticeTitle = await createText(
    "최근 공지사항",
    19,
    "Bold"
  );

  noticeTitle.x = 20;
  noticeTitle.y = 660;

  screen.appendChild(noticeTitle);

  const noticeCard = createCard(350, 88, 14);

  noticeCard.name = "최근 공지사항 카드";
  noticeCard.x = 20;
  noticeCard.y = 694;

  const notice1 = await createText(
    "노트북 백신 설치 안내",
    14,
    "Medium"
  );

  notice1.x = 16;
  notice1.y = 14;

  noticeCard.appendChild(notice1);

  const noticeDate1 = await createText(
    "7.22",
    12,
    "Regular",
    SUB_TEXT_COLOR
  );

  noticeDate1.x = 299;
  noticeDate1.y = 16;

  noticeCard.appendChild(noticeDate1);

  const divider = createDivider(318);

  divider.x = 16;
  divider.y = 43;

  noticeCard.appendChild(divider);

  const notice2 = await createText(
    "이번 주 식단 변경 안내",
    14,
    "Medium"
  );

  notice2.x = 16;
  notice2.y = 56;

  noticeCard.appendChild(notice2);

  const noticeDate2 = await createText(
    "7.21",
    12,
    "Regular",
    SUB_TEXT_COLOR
  );

  noticeDate2.x = 299;
  noticeDate2.y = 58;

  noticeCard.appendChild(noticeDate2);

  screen.appendChild(noticeCard);

  // 하단 내비게이션
  const navigation = figma.createFrame();

  navigation.name = "하단 내비게이션";
  navigation.resize(390, 62);
  navigation.x = 0;
  navigation.y = 782;
  navigation.clipsContent = false;

  navigation.fills = [
    {
      type: "SOLID",
      color: WHITE,
    },
  ];

  navigation.effects = [
    {
      type: "DROP_SHADOW",
      color: {
        r: 0,
        g: 0,
        b: 0,
        a: 0.06,
      },
      offset: {
        x: 0,
        y: -2,
      },
      radius: 8,
      spread: 0,
      visible: true,
      blendMode: "NORMAL",
    },
  ];

  const navItems: NavItemData[] = [
    {
      label: "홈",
      iconType: "home",
      centerX: 48,
      active: true,
    },
    {
      label: "공지",
      iconType: "bell",
      centerX: 145,
      active: false,
    },
    {
      label: "챗봇",
      iconType: "message",
      centerX: 242,
      active: false,
    },
    {
      label: "민원",
      iconType: "megaphone",
      centerX: 339,
      active: false,
    },
  ];

  for (const item of navItems) {
    await createNavigationItem(item, navigation);
  }

  screen.appendChild(navigation);

  // 캔버스에 추가
  figma.currentPage.appendChild(screen);
  figma.currentPage.selection = [screen];
  figma.viewport.scrollAndZoomIntoView([screen]);

  figma.notify(
    "벡터 아이콘이 적용된 학생 메인 화면이 생성되었습니다."
  );

  figma.closePlugin();
}

main().catch((error: unknown) => {
  console.error(error);

  figma.notify(
    "화면 생성 중 오류가 발생했습니다."
  );

  figma.closePlugin();
});